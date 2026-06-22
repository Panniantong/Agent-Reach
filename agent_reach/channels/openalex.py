# -*- coding: utf-8 -*-
"""OpenAlex — the largest open scholarly index. 250M+ papers, REST API, free.

API docs: https://docs.openalex.org/
Base URL: https://api.openalex.org/works
No API key required. Polite use: max 10 req/s.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

from .base import Channel

_BASE = "https://api.openalex.org/works"
_UA = "mailto:agent-reach@example.com"
_TIMEOUT = 30


@dataclass
class OAPaper:
    """A paper from OpenAlex."""

    openalex_id: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    year: int = 0
    cited_by_count: int = 0
    doi: str = ""
    arxiv_id: str = ""
    pdf_url: str = ""
    topics: List[str] = field(default_factory=list)
    venue: str = ""
    type: str = ""  # article, preprint, book-chapter, etc.

    def to_dict(self) -> dict:
        return {
            "openalex_id": self.openalex_id,
            "title": self.title,
            "authors": self.authors,
            "abstract": (self.abstract or "")[:500],
            "year": self.year,
            "cited_by_count": self.cited_by_count,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "pdf_url": self.pdf_url,
            "topics": self.topics,
            "venue": self.venue,
            "type": self.type,
        }


def _api_get(path: str, params: dict = None, timeout: int = _TIMEOUT) -> dict:
    """GET OpenAlex API, return parsed JSON."""
    if params is None:
        params = {}
    # OpenAlex polite pool: add mailto
    params.setdefault("mailto", "agent-reach@example.com")
    qs = urllib.parse.urlencode(params)
    url = f"{_BASE}{path}?{qs}" if "?" not in path else f"{_BASE}{path}&{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


def _parse_paper(raw: dict) -> OAPaper:
    """Parse OpenAlex work object into OAPaper."""
    p = OAPaper()
    p.openalex_id = raw.get("id", "").split("/")[-1] if raw.get("id") else ""
    p.title = raw.get("title") or raw.get("display_name", "") or ""
    p.abstract = ""
    # Abstract is in abstract_inverted_index
    ai = raw.get("abstract_inverted_index") or {}
    if ai:
        try:
            words = [""] * max(idx for indices in ai.values() for idx in indices)
            for word, indices in ai.items():
                for idx in indices:
                    words[idx] = word
            p.abstract = " ".join(words)
        except Exception:
            pass
    p.year = raw.get("publication_year") or 0
    p.cited_by_count = raw.get("cited_by_count") or 0
    p.doi = raw.get("doi", "").replace("https://doi.org/", "") if raw.get("doi") else ""
    p.type = raw.get("type", "")

    # Authors
    for a in raw.get("authorships") or []:
        name = (a.get("author") or {}).get("display_name", "")
        if name:
            p.authors.append(name)

    # Topics
    for t in raw.get("topics") or []:
        name = t.get("display_name", "")
        if name:
            p.topics.append(name)

    # Venue
    venue = raw.get("primary_location") or {}
    source = venue.get("source") or {}
    p.venue = source.get("display_name", "")

    # PDF URL
    oa = raw.get("open_access") or {}
    p.pdf_url = oa.get("oa_url", "") or raw.get("best_oa_location", {}).get("pdf_url", "")

    # External IDs
    for loc in [raw.get("primary_location")] + (raw.get("locations") or []):
        if loc and loc.get("pdf_url"):
            p.pdf_url = p.pdf_url or loc["pdf_url"]
        landing = (loc or {}).get("landing_page_url", "")
        if "arxiv.org" in landing:
            p.arxiv_id = landing.split("/abs/")[-1] if "/abs/" in landing else ""

    return p


def search_openalex(
    query: str,
    limit: int = 15,
    year: str = "",
    sort: str = "cited_by_count:desc",
    timeout: int = _TIMEOUT,
) -> List[OAPaper]:
    """Search OpenAlex.

    Args:
        query: Search terms.
        limit: Max results (1-200).
        year: Filter like "2023-2025".
        sort: Sort order. Default: most cited.
        timeout: HTTP timeout.
    """
    params = {
        "search": query,
        "per_page": str(min(limit, 200)),
        "sort": sort,
    }
    if year:
        # OpenAlex uses publication_year:2023-2025
        params["filter"] = f"publication_year:{year}"

    data = _api_get("", params, timeout=timeout)
    results = data.get("results") or []
    return [_parse_paper(r) for r in results]


class OpenAlexChannel(Channel):
    name = "openalex"
    description = "OpenAlex 学术索引（2.5亿论文）"
    backends = ["OpenAlex API (public)"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return "openalex.org" in url.lower() or "doi.org" in url.lower()

    def check(self, config=None):
        """Probe with a lightweight query."""
        data = _api_get("", {"search": "test", "per_page": "1"}, timeout=10)
        meta = data.get("meta") or {}
        if meta.get("count", 0) >= 0:
            count = meta.get("count", 0)
            self.active_backend = self.backends[0]
            return "ok", f"OpenAlex API 可用（总计 {count/1e6:.0f}M 篇论文，免费）"
        self.active_backend = None
        return "warn", "OpenAlex API 连接失败"

    def search(self, query: str, limit: int = 15, year: str = "", config=None) -> List[dict]:
        papers = search_openalex(query, limit=limit, year=year)
        return [p.to_dict() for p in papers]

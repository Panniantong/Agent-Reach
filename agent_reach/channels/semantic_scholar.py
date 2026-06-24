# -*- coding: utf-8 -*-
"""Semantic Scholar — search academic papers with citation and influence data.

Free public API. Optional API key for higher rate limits.
API docs: https://api.semanticscholar.org/api-docs/
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from agent_reach.probe import probe_command

from .base import Channel

_S2_API = "https://api.semanticscholar.org/graph/v1"
_UA = "agent-reach/1.0"
_TIMEOUT = 30

# Fields to request from S2 API (minimize response size)
_PAPER_FIELDS = (
    "paperId,title,abstract,year,authors,"
    "citationCount,influentialCitationCount,"
    "venue,journal,publicationTypes,"
    "externalIds,url,openAccessPdf,"
    "fieldsOfStudy,publicationDate,"
    "tldr,references.title,references.paperId"
)

_SEARCH_FIELDS = (
    "paperId,title,abstract,year,authors,"
    "citationCount,influentialCitationCount,"
    "venue,journal,externalIds,url,"
    "openAccessPdf,fieldsOfStudy,publicationDate,tldr"
)


@dataclass
class S2Author:
    author_id: str = ""
    name: str = ""

    def to_dict(self) -> dict:
        return {"author_id": self.author_id, "name": self.name}


@dataclass
class S2Venue:
    name: str = ""
    type: str = ""  # journal, conference, etc.

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.type}


@dataclass
class S2Paper:
    """A paper fetched from Semantic Scholar."""

    paper_id: str = ""
    title: str = ""
    abstract: str = ""
    year: int = 0
    authors: List[S2Author] = field(default_factory=list)
    citation_count: int = 0
    influential_citation_count: int = 0
    venue: str = ""
    journal: str = ""
    fields_of_study: List[str] = field(default_factory=list)
    publication_date: str = ""
    url: str = ""
    open_access_pdf: str = ""
    arxiv_id: str = ""
    doi: str = ""
    tldr: str = ""  # TL;DR summary from S2

    def to_dict(self) -> dict:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "abstract": self.abstract or "",
            "year": self.year,
            "authors": [a.to_dict() for a in self.authors],
            "citation_count": self.citation_count,
            "influential_citation_count": self.influential_citation_count,
            "venue": self.venue,
            "journal": self.journal,
            "fields_of_study": self.fields_of_study,
            "publication_date": self.publication_date,
            "url": self.url,
            "open_access_pdf": self.open_access_pdf or "",
            "arxiv_id": self.arxiv_id,
            "doi": self.doi,
            "tldr": self.tldr or "",
        }


def _api_get(endpoint: str, params: dict, api_key: str = "", timeout: int = _TIMEOUT) -> dict:
    """GET a Semantic Scholar API endpoint, return parsed JSON."""
    qs = urllib.parse.urlencode(params)
    url = f"{endpoint}?{qs}" if qs else endpoint
    headers = {"User-Agent": _UA}
    if api_key:
        headers["x-api-key"] = api_key
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


def _parse_paper(raw: dict) -> S2Paper:
    """Parse a raw S2 API paper dict into S2Paper."""
    p = S2Paper()
    p.paper_id = raw.get("paperId", "")
    p.title = raw.get("title") or ""
    p.abstract = raw.get("abstract") or ""
    p.year = raw.get("year") or 0
    p.citation_count = raw.get("citationCount") or 0
    p.influential_citation_count = raw.get("influentialCitationCount") or 0
    p.fields_of_study = raw.get("fieldsOfStudy") or []
    p.publication_date = raw.get("publicationDate") or ""
    p.url = raw.get("url") or ""
    p.tldr = (raw.get("tldr") or {}).get("text", "")

    # Venue
    venue = raw.get("venue") or {}
    if isinstance(venue, dict):
        p.venue = venue.get("name", venue.get("text", ""))

    # Journal
    journal = raw.get("journal") or {}
    if isinstance(journal, dict):
        p.journal = journal.get("name", "")

    # Authors
    for a in raw.get("authors") or []:
        p.authors.append(S2Author(author_id=a.get("authorId", ""), name=a.get("name", "")))

    # External IDs
    ext = raw.get("externalIds") or {}
    p.arxiv_id = ext.get("ArXiv", "")
    p.doi = ext.get("DOI", "")

    # Open access PDF
    oa = raw.get("openAccessPdf") or {}
    p.open_access_pdf = oa.get("url", "") if oa else ""

    return p


def search_semantic_scholar(
    query: str,
    limit: int = 10,
    offset: int = 0,
    year: str = "",
    fields_of_study: str = "",
    api_key: str = "",
    timeout: int = _TIMEOUT,
) -> List[S2Paper]:
    """Search Semantic Scholar.

    Args:
        query: Search query string.
        limit: Max results (1-100).
        offset: Pagination offset.
        year: Year range filter (e.g., "2020-2025").
        fields_of_study: Comma-separated (e.g., "Computer Science,Engineering").
        api_key: Optional API key for higher rate limits.
        timeout: HTTP timeout.

    Returns:
        List of S2Paper.
    """
    endpoint = f"{_S2_API}/paper/search"
    params = {
        "query": query,
        "limit": str(min(limit, 100)),
        "offset": str(offset),
        "fields": _SEARCH_FIELDS,
    }
    if year:
        params["year"] = year
    if fields_of_study:
        params["fieldsOfStudy"] = fields_of_study

    data = _api_get(endpoint, params, api_key=api_key, timeout=timeout)
    raw_papers = data.get("data") or []
    return [_parse_paper(p) for p in raw_papers]


def get_paper_s2(
    paper_id: str,
    api_key: str = "",
    timeout: int = _TIMEOUT,
) -> Optional[S2Paper]:
    """Fetch a single paper by Semantic Scholar ID or DOI/ArXiv ID.

    Supports: S2 paper ID, DOI:xxx, ArXiv:xxx, or URL.
    """
    endpoint = f"{_S2_API}/paper/{urllib.parse.quote(paper_id, safe='')}"
    data = _api_get(endpoint, {"fields": _PAPER_FIELDS}, api_key=api_key, timeout=timeout)
    if not data or "paperId" not in data:
        return None
    return _parse_paper(data)


def get_citations(
    paper_id: str,
    limit: int = 20,
    api_key: str = "",
    timeout: int = _TIMEOUT,
) -> List[S2Paper]:
    """Get papers that cite this paper."""
    endpoint = f"{_S2_API}/paper/{paper_id}/citations"
    params = {"limit": str(min(limit, 500)), "fields": _SEARCH_FIELDS}
    data = _api_get(endpoint, params, api_key=api_key, timeout=timeout)
    raw = data.get("data") or []
    return [_parse_paper(p.get("citingPaper", p)) for p in raw]


def get_references(
    paper_id: str,
    limit: int = 20,
    api_key: str = "",
    timeout: int = _TIMEOUT,
) -> List[S2Paper]:
    """Get papers referenced by this paper."""
    endpoint = f"{_S2_API}/paper/{paper_id}/references"
    params = {"limit": str(min(limit, 500)), "fields": _SEARCH_FIELDS}
    data = _api_get(endpoint, params, api_key=api_key, timeout=timeout)
    raw = data.get("data") or []
    return [_parse_paper(p.get("citedPaper", p)) for p in raw]


class SemanticScholarChannel(Channel):
    name = "semantic_scholar"
    description = "Semantic Scholar 学术搜索（含引用数据）"
    backends = ["Semantic Scholar API (public)"]
    tier = 0  # zero-config — public API works without key

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "semanticscholar.org" in d

    def check(self, config=None):
        """Probe S2 API with a lightweight query. Config key semantic_scholar_api_key
        is optional; rate limits are lower without it but the API still works."""
        api_key = config.get("semantic_scholar_api_key") if config else ""
        data = _api_get(
            f"{_S2_API}/paper/search",
            {"query": "test", "limit": "1", "fields": "paperId"},
            api_key=api_key,
            timeout=10,
        )
        if data and "data" in data:
            self.active_backend = self.backends[0]
            limit_note = "" if api_key else "（无 Key 限 100次/5分钟，对科研场景够用）"
            return "ok", (
                f"Semantic Scholar API 可用{limit_note}"
                "（搜索论文、引用数据、影响力评分、TLDR摘要）"
            )
        self.active_backend = None
        return "warn", "Semantic Scholar API 连接失败，可能需要代理"

    def search(
        self,
        query: str,
        limit: int = 10,
        year: str = "",
        fields_of_study: str = "",
        config=None,
    ) -> List[dict]:
        """Search papers. Returns list of dicts."""
        api_key = config.get("semantic_scholar_api_key") if config else ""
        papers = search_semantic_scholar(
            query,
            limit=limit,
            year=year,
            fields_of_study=fields_of_study,
            api_key=api_key,
        )
        return [p.to_dict() for p in papers]

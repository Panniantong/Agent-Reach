# -*- coding: utf-8 -*-
"""CORE — world's largest open access papers aggregator. 30M+ papers.

API docs: https://core.ac.uk/services/api
Requires a free API key: https://core.ac.uk/services/api#register
Without key: still works for search (lower rate limit).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

from .base import Channel

_BASE = "https://api.core.ac.uk/v3/search/works"
_UA = "agent-reach/1.0"
_TIMEOUT = 30


@dataclass
class COREPaper:
    core_id: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    year: int = 0
    doi: str = ""
    download_url: str = ""
    publisher: str = ""
    language: str = ""

    def to_dict(self) -> dict:
        return {
            "core_id": self.core_id,
            "title": self.title,
            "authors": self.authors,
            "abstract": (self.abstract or "")[:500],
            "year": self.year,
            "doi": self.doi,
            "download_url": self.download_url,
            "publisher": self.publisher,
            "language": self.language,
        }


def search_core(
    query: str,
    limit: int = 15,
    api_key: str = "",
    timeout: int = _TIMEOUT,
) -> List[COREPaper]:
    """Search CORE for open access papers.

    Args:
        query: Search terms.
        limit: Max results (1-100).
        api_key: Optional API key for higher rate limits.
    """
    body = json.dumps({
        "q": query,
        "limit": min(limit, 100),
        "scroll": False,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "User-Agent": _UA,
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(_BASE, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []

    results = data.get("results") or []
    papers = []
    for r in results:
        p = COREPaper()
        p.core_id = str(r.get("id", ""))
        p.title = r.get("title", "") or ""
        p.abstract = r.get("abstract", "") or ""
        p.year = r.get("yearPublished") or 0
        p.doi = r.get("doi", "")
        p.download_url = r.get("downloadUrl", "") or r.get("sourceFulltextUrls", [None])[0] or ""
        p.publisher = r.get("publisher", "")
        p.language = (r.get("language") or {}).get("name", "")
        for a in r.get("authors") or []:
            name = a.get("name", "")
            if name:
                p.authors.append(name)
        papers.append(p)

    return papers


class COREChannel(Channel):
    name = "core"
    description = "CORE 开放获取论文（3000万篇）"
    backends = ["CORE API (public)"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return "core.ac.uk" in url.lower()

    def check(self, config=None):
        """Probe CORE API."""
        try:
            body = json.dumps({"q": "test", "limit": 1, "scroll": False}).encode("utf-8")
            req = urllib.request.Request(
                _BASE, data=body,
                headers={"Content-Type": "application/json", "User-Agent": _UA},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                total = data.get("totalHits", 0)
                if total >= 0:
                    self.active_backend = self.backends[0]
                    return "ok", f"CORE API 可用（总计 {total/1e6:.0f}M+ 开放获取论文）"
        except Exception:
            pass
        self.active_backend = None
        return "warn", "CORE API 连接失败"

    def search(self, query: str, limit: int = 15, config=None) -> List[dict]:
        api_key = config.get("core_api_key") if config else ""
        papers = search_core(query, limit=limit, api_key=api_key)
        return [p.to_dict() for p in papers]

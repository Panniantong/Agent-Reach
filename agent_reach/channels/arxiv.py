# -*- coding: utf-8 -*-
"""arXiv — search academic papers via the public arXiv API.

Free, no API key required. Rate limit: 1 request per 3 seconds (polite use).
API docs: https://info.arxiv.org/help/api/
"""

from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from .base import Channel

_ARXIV_API = "http://export.arxiv.org/api/query"
_UA = "agent-reach/1.0"
_TIMEOUT = 30

# arXiv API namespaces
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


@dataclass
class ArxivPaper:
    """A paper fetched from arXiv."""

    arxiv_id: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    published: str = ""  # ISO date
    updated: str = ""
    pdf_url: str = ""
    abs_url: str = ""
    categories: List[str] = field(default_factory=list)
    comment: str = ""  # e.g. "Accepted at ICML 2025"
    primary_category: str = ""
    doi: str = ""

    def to_dict(self) -> dict:
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title.strip().replace("\n", " "),
            "authors": self.authors,
            "abstract": self.abstract.strip().replace("\n", " "),
            "published": self.published,
            "updated": self.updated,
            "pdf_url": self.pdf_url,
            "abs_url": self.abs_url,
            "categories": self.categories,
            "comment": self.comment,
            "primary_category": self.primary_category,
            "doi": self.doi,
        }


def _text(el, tag: str) -> str:
    """Get text content of a child element in the Atom namespace."""
    child = el.find(f"atom:{tag}", _NS)
    return (child.text or "").strip() if child is not None and child.text else ""


def _arxiv_text(el, tag: str) -> str:
    """Get text content of a child element in the arXiv namespace."""
    child = el.find(f"arxiv:{tag}", _NS)
    return (child.text or "").strip() if child is not None and child.text else ""


def _parse_paper(entry) -> ArxivPaper:
    """Parse an Atom entry into an ArxivPaper."""
    paper = ArxivPaper()

    # ID: e.g. "http://arxiv.org/abs/2301.12345v2"
    id_url = _text(entry, "id")
    paper.arxiv_id = id_url.split("/abs/")[-1] if "/abs/" in id_url else id_url

    paper.title = _text(entry, "title")
    paper.abstract = _text(entry, "summary")
    paper.published = _text(entry, "published")
    paper.updated = _text(entry, "updated")
    paper.comment = _arxiv_text(entry, "comment")

    # Authors
    for author in entry.findall("atom:author", _NS):
        name = _text(author, "name")
        if name:
            paper.authors.append(name)

    # Links
    for link in entry.findall("atom:link", _NS):
        href = link.attrib.get("href", "")
        rel = link.attrib.get("rel", "")
        title = link.attrib.get("title", "")
        if rel == "alternate":
            paper.abs_url = href
        elif title == "pdf":
            paper.pdf_url = href
        elif rel == "related" and "doi.org" in href:
            paper.doi = href

    # Categories
    for cat in entry.findall("atom:category", _NS):
        term = cat.attrib.get("term", "")
        if term:
            paper.categories.append(term)

    paper.primary_category = (
        entry.find("arxiv:primary_category", _NS).attrib.get("term", "")
        if entry.find("arxiv:primary_category", _NS) is not None
        else ""
    )

    return paper


def search_arxiv(
    query: str,
    max_results: int = 10,
    start: int = 0,
    sort_by: str = "relevance",
    timeout: int = _TIMEOUT,
) -> List[ArxivPaper]:
    """Search arXiv and return a list of ArxivPaper.

    Args:
        query: Search query (supports arXiv syntax: ti:title, au:author, all:text).
        max_results: Max papers to return.
        start: Offset for pagination.
        sort_by: "relevance", "lastUpdatedDate", or "submittedDate".
        timeout: HTTP request timeout in seconds.

    Returns:
        List of ArxivPaper (empty list on error).
    """
    params = {
        "search_query": query,
        "start": str(start),
        "max_results": str(min(max_results, 100)),
        "sortBy": sort_by,
    }
    url = f"{_ARXIV_API}?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except Exception:
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    papers = []
    for entry in root.findall("atom:entry", _NS):
        papers.append(_parse_paper(entry))
    return papers


def get_paper(arxiv_id: str, timeout: int = _TIMEOUT) -> Optional[ArxivPaper]:
    """Fetch a single paper by arXiv ID."""
    results = search_arxiv(f"id:{arxiv_id}", max_results=1, timeout=timeout)
    return results[0] if results else None


class ArxivChannel(Channel):
    name = "arxiv"
    description = "arXiv 学术论文搜索"
    backends = ["arXiv API (public)"]
    tier = 0  # zero config — public API, no key needed

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "arxiv.org" in d

    def check(self, config=None):
        """Probe the arXiv API with a lightweight query."""
        import urllib.request

        url = f"{_ARXIV_API}?search_query=all:test&max_results=1"
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    self.active_backend = self.backends[0]
                    return "ok", (
                        "arXiv API 可用（搜索论文、摘要、PDF链接，免费无需API Key）"
                    )
                return "warn", f"arXiv API 返回 HTTP {resp.status}"
        except Exception as e:
            self.active_backend = None
            return "warn", f"arXiv API 连接失败：{e}"

    def search(self, query: str, max_results: int = 10, sort_by: str = "relevance") -> List[dict]:
        """Search arXiv papers. Returns list of dicts."""
        papers = search_arxiv(query, max_results=max_results, sort_by=sort_by)
        return [p.to_dict() for p in papers]

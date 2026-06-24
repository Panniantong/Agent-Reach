# -*- coding: utf-8 -*-
"""DBLP — computer science bibliography. 7.5M+ papers, author-venue links.

Search API: https://dblp.org/search/publ/api
No API key required.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional

from .base import Channel

_BASE = "https://dblp.org/search/publ/api"
_UA = "agent-reach/1.0"
_TIMEOUT = 30


@dataclass
class DBLPPaper:
    dblp_key: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    year: int = 0
    venue: str = ""
    doi: str = ""
    url: str = ""

    def to_dict(self) -> dict:
        return {
            "dblp_key": self.dblp_key,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "venue": self.venue,
            "doi": self.doi,
            "url": self.url,
        }


def search_dblp(
    query: str,
    max_results: int = 15,
    timeout: int = _TIMEOUT,
) -> List[DBLPPaper]:
    """Search DBLP for CS papers."""
    params = urllib.parse.urlencode({
        "q": query,
        "h": str(min(max_results, 1000)),
        "format": "xml",
    })
    url = f"{_BASE}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            root = ET.fromstring(resp.read())
    except Exception:
        return []

    papers = []
    for hit in root.findall(".//hit"):
        try:
            papers.append(_parse_hit(hit))
        except Exception:
            continue
    return papers


def _parse_hit(hit) -> DBLPPaper:
    p = DBLPPaper()

    # Key
    key_el = hit.find("key")
    if key_el is not None:
        p.dblp_key = key_el.text or ""

    # URL
    url_el = hit.find("url")
    if url_el is not None:
        p.url = url_el.text or ""

    # Title
    title_el = hit.find(".//title")
    if title_el is not None and title_el.text:
        p.title = title_el.text

    # Authors
    for author in hit.findall(".//author"):
        if author.text:
            p.authors.append(author.text)

    # Year
    year_el = hit.find(".//year")
    if year_el is not None and year_el.text:
        try:
            p.year = int(year_el.text)
        except ValueError:
            pass

    # Venue from info node
    info = hit.find(".//info")
    if info is not None:
        for child in info:
            if child.text and child.tag != "title" and child.tag != "author":
                p.venue = p.venue or child.text

    return p


class DBLPChannel(Channel):
    name = "dblp"
    description = "DBLP 计算机科学文献库"
    backends = ["DBLP Search API (public)"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return "dblp.org" in url.lower()

    def check(self, config=None):
        """Probe DBLP with a lightweight search."""
        try:
            url = f"{_BASE}?q=test&h=1&format=json"
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                if "result" in data:
                    self.active_backend = self.backends[0]
                    return "ok", "DBLP Search API 可用（750万篇计算机论文，免费）"
        except Exception:
            pass
        self.active_backend = None
        return "warn", "DBLP API 连接失败"

    def search(self, query: str, max_results: int = 15, config=None) -> List[dict]:
        papers = search_dblp(query, max_results=max_results)
        return [p.to_dict() for p in papers]

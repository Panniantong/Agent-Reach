# -*- coding: utf-8 -*-
"""Papers With Code — ML papers + code + benchmarks.

Unofficial portal API (same endpoints the website uses).
No authentication required. Rate limit: polite use.

Data includes: paper title, authors, abstract, GitHub links, SOTA rankings.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

from .base import Channel

_BASE = "https://paperswithcode.com/api/v1"
_UA = "agent-reach/1.0"
_TIMEOUT = 30


@dataclass
class PWCPaper:
    pwc_id: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    year: int = 0
    url: str = ""
    arxiv_id: str = ""
    github_urls: List[str] = field(default_factory=list)
    tasks: List[str] = field(default_factory=list)
    datasets: List[str] = field(default_factory=list)
    stars: int = 0  # GitHub stars of official implementation

    def to_dict(self) -> dict:
        return {
            "pwc_id": self.pwc_id,
            "title": self.title,
            "authors": self.authors,
            "abstract": (self.abstract or "")[:500],
            "year": self.year,
            "url": self.url,
            "arxiv_id": self.arxiv_id,
            "github_urls": self.github_urls,
            "tasks": self.tasks,
            "datasets": self.datasets,
            "stars": self.stars,
        }


def _api_get(endpoint: str, params: dict = None, timeout: int = _TIMEOUT) -> dict:
    """GET Papers With Code API."""
    if params is None:
        params = {}
    qs = urllib.parse.urlencode(params)
    url = f"{_BASE}{endpoint}?{qs}" if qs else f"{_BASE}{endpoint}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def search_pwc(
    query: str,
    limit: int = 15,
    timeout: int = _TIMEOUT,
) -> List[PWCPaper]:
    """Search Papers With Code.

    Returns papers with GitHub repos and benchmark data.
    """
    data = _api_get("/papers/", {"q": query, "items_per_page": str(min(limit, 50))})
    results = data.get("results") or []

    papers = []
    for r in results:
        p = PWCPaper()
        p.pwc_id = r.get("id", "")
        p.title = r.get("title", "") or ""
        p.abstract = r.get("abstract", "") or ""
        p.url = f"https://paperswithcode.com{r.get('url_abs', '')}"
        p.year = r.get("published", {}).get("year", 0) if isinstance(r.get("published"), dict) else 0
        p.arxiv_id = r.get("arxiv_id", "") or ""

        # Authors
        for a in r.get("authors", []):
            if isinstance(a, str):
                p.authors.append(a)
            elif isinstance(a, dict):
                p.authors.append(a.get("name", ""))

        # GitHub repos
        for repo in r.get("repos", [])[:3]:
            url = repo.get("url", "") if isinstance(repo, dict) else str(repo)
            if url and "github.com" in url:
                p.github_urls.append(url)
            p.stars = repo.get("stars", 0) if isinstance(repo, dict) else 0

        # Tasks and datasets from evaluation tables
        seen_tasks = set()
        seen_datasets = set()
        for ev in r.get("evaluation_tables", []):
            task = ev.get("task", "") if isinstance(ev, dict) else ""
            if task and task not in seen_tasks:
                p.tasks.append(task)
                seen_tasks.add(task)
            dataset = ev.get("dataset", "") if isinstance(ev, dict) else ""
            if dataset and dataset not in seen_datasets:
                p.datasets.append(dataset)
                seen_datasets.add(dataset)

        papers.append(p)
    return papers


class PapersWithCodeChannel(Channel):
    name = "papers_with_code"
    description = "Papers With Code（ML论文+代码+排行榜）"
    backends = ["PwC API (public)"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return "paperswithcode.com" in url.lower()

    def check(self, config=None):
        """Probe PwC API."""
        try:
            data = _api_get("/papers/", {"q": "transformer", "items_per_page": "1"}, timeout=10)
            if data.get("count", 0) >= 0:
                count = data.get("count", 0)
                self.active_backend = self.backends[0]
                return "ok", f"Papers With Code API 可用（{count} 篇ML论文，含代码和排行榜）"
        except Exception:
            pass
        self.active_backend = None
        return "warn", "Papers With Code API 连接失败"

    def search(self, query: str, limit: int = 15, config=None) -> List[dict]:
        papers = search_pwc(query, limit=limit)
        return [p.to_dict() for p in papers]

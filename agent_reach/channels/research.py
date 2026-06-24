# -*- coding: utf-8 -*-
"""Research Channel — multi-source academic paper search with quality ranking.

Aggregates arXiv + Semantic Scholar, deduplicates, scores, and ranks
papers by quality signals (citations, venue prestige, recency, openness).

Zero-config tier 0: both backends have free public APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from agent_reach.probe import probe_command

from .base import Channel


class ResearchChannel(Channel):
    """Academic research: search, rank, and analyze papers across sources."""

    name = "research"
    description = "学术论文搜索与质量分析"
    backends = ["arXiv API", "Semantic Scholar API"]
    tier = 0  # zero-config — both backends have free public APIs

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return any(
            domain in d
            for domain in (
                "arxiv.org",
                "semanticscholar.org",
                "scholar.google.com",
                "acm.org",
                "ieee.org",
                "springer.com",
                "sciencedirect.com",
                "nature.com",
                "science.org",
                "pnas.org",
                "jmlr.org",
                "openreview.net",
                "aclweb.org",
                "nips.cc",
                "neurips.cc",
                "mlr.press",
                "pmlr",
            )
        )

    def check(self, config=None):
        """Check arXiv and S2 backend availability. At least one must work."""
        import urllib.request

        self.active_backend = None
        available = []

        # Probe arXiv
        try:
            url = "http://export.arxiv.org/api/query?search_query=all:test&max_results=1"
            req = urllib.request.Request(
                url, headers={"User-Agent": "agent-reach/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    available.append("arXiv API")
        except Exception:
            pass

        # Probe Semantic Scholar
        try:
            import json

            url = (
                "https://api.semanticscholar.org/graph/v1/paper/search"
                "?query=test&limit=1&fields=paperId"
            )
            req = urllib.request.Request(
                url, headers={"User-Agent": "agent-reach/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                if "data" in data:
                    available.append("Semantic Scholar API")
        except Exception:
            pass

        if available:
            self.active_backend = " + ".join(available)
            return "ok", (
                f"{' + '.join(available)} 均可用。支持：主题搜索 → "
                "去重合并 → 引用/会议/时效打分排序 → 论文分析"
            )
        self.active_backend = None
        return "warn", (
            "学术搜索后端均不可达（可能需要代理访问外网）。"
            "两个后端都是免费公开 API，无需 API Key。"
        )

    # ------------------------------------------------------------------ #
    # Public API — agents call these
    # ------------------------------------------------------------------ #

    def search(
        self,
        topic: str,
        max_results: int = 15,
        year: str = "",
        fields_of_study: str = "",
        emphasis: str = "balanced",
        config=None,
    ) -> List[dict]:
        """Search for the best papers on a topic.

        Args:
            topic: Research topic, e.g. "large language model reasoning".
            max_results: Max papers to return (default 15, max 50).
            year: Year range, e.g. "2022-2025" or "2023-".
            fields_of_study: Comma-separated, e.g. "Computer Science".
            emphasis: Ranking emphasis — "balanced", "latest", "classic", "open".
            config: Optional Config instance.

        Returns:
            List of paper dicts, ranked by quality, best first.
        """
        from agent_reach.research.analyzer import rank_papers, research_topic

        # Map emphasis to weights
        weight_map = {
            "balanced": (0.40, 0.30, 0.20, 0.10),
            "latest": (0.20, 0.20, 0.50, 0.10),
            "classic": (0.60, 0.25, 0.05, 0.10),
            "open": (0.30, 0.20, 0.20, 0.30),
        }
        weights = weight_map.get(emphasis, weight_map["balanced"])

        # Fetch and merge
        results = research_topic(
            topic,
            max_results=min(max_results, 50),
            year=year,
            fields_of_study=fields_of_study,
            config=config,
        )

        # Re-rank with emphasis weights
        ranked = rank_papers(
            results,
            citation_weight=weights[0],
            venue_weight=weights[1],
            recency_weight=weights[2],
            openness_weight=weights[3],
        )

        return [r.to_dict() for r in ranked[:max_results]]

    def analyze(self, paper_title: str, config=None) -> dict:
        """Analyze a single paper — get detailed metadata and quality score.

        Args:
            paper_title: Paper title (exact match works best).
            config: Optional Config instance.

        Returns:
            Dict with enriched metadata and quality assessment.
        """
        from agent_reach.research.analyzer import analyze_paper

        return analyze_paper(paper_title, config=config)

    def summary(self, results: List[dict]) -> str:
        """Produce a human-readable summary of search results.

        Args:
            results: List of paper dicts from search().

        Returns:
            Formatted summary string.
        """
        if not results:
            return "No papers found."

        excellent = sum(
            1 for r in results if (r.get("quality") or {}).get("rating") == "excellent"
        )
        good = sum(
            1 for r in results if (r.get("quality") or {}).get("rating") == "good"
        )

        lines = [
            f"Found {len(results)} papers.",
            f"  Excellent (≥0.70): {excellent}",
            f"  Good      (≥0.45): {good}",
            "",
        ]

        for i, r in enumerate(results[:5], 1):
            q = r.get("quality") or {}
            lines.append(
                f"  {i}. [{q.get('rating', '?').upper()}] "
                f"{r['title']} ({r.get('year', '?')})"
            )
            authors = ", ".join(r.get("authors", [])[:3])
            if len(r.get("authors", [])) > 3:
                authors += " et al."
            lines.append(f"     {authors}")
            if r.get("tldr"):
                lines.append(f"     TL;DR: {r['tldr']}")
            lines.append(
                f"     Citations: {r.get('citation_count', 0)} | "
                f"Venue: {r.get('venue', 'unknown')} | "
                f"Score: {q.get('overall', 'N/A')}"
            )
            if r.get("pdf_url"):
                lines.append(f"     PDF: {r['pdf_url']}")
            lines.append("")

        return "\n".join(lines)

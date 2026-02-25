# -*- coding: utf-8 -*-
"""
AgentReach — the unified entry point.

Pure glue: routes URLs to the right channel, routes searches to the right engine.
Every channel is a thin wrapper around an external tool. Swap any backend anytime.

Usage:
    from agent_reach import AgentReach

    eyes = AgentReach()
    content = await eyes.read("https://github.com/openai/gpt-4")
    results = await eyes.search("AI agent framework")
"""

import asyncio
from typing import Any, Dict, List, Optional

from agent_reach.config import Config
from agent_reach.channels import get_channel_for_url, get_channel, get_all_channels


class AgentReach:
    """Give your AI Agent eyes to see the entire internet."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()

    # ── Reading ─────────────────────────────────────────

    async def read(self, url: str) -> Dict[str, Any]:
        """
        Read content from any URL. Auto-detects platform.

        Supported: Web, GitHub, Reddit, Twitter, YouTube,
        Bilibili, RSS, and more.

        Returns:
            Dict with title, content, url, author, platform, etc.
        """
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        channel = get_channel_for_url(url)
        result = await channel.read(url, config=self.config)
        return result.to_dict()

    async def read_batch(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Read multiple URLs concurrently."""
        tasks = [self.read(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if not isinstance(r, Exception)]

    def detect_platform(self, url: str) -> str:
        """Detect what platform a URL belongs to."""
        channel = get_channel_for_url(url)
        return channel.name

    # ── Searching ───────────────────────────────────────

    async def search(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """Semantic web search via Exa."""
        ch = get_channel("exa_search")
        results = await ch.search(query, config=self.config, limit=num_results)
        return [r.to_dict() for r in results]

    async def search_reddit(self, query: str, subreddit: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Search Reddit via Exa (bypasses IP blocks)."""
        ch = get_channel("exa_search")
        q = f"site:reddit.com/r/{subreddit} {query}" if subreddit else f"site:reddit.com {query}"
        results = await ch.search(q, config=self.config, limit=limit)
        return [r.to_dict() for r in results]

    async def search_github(self, query: str, language: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Search GitHub repositories."""
        ch = get_channel("github")
        results = await ch.search(query, config=self.config, language=language, limit=limit)
        return [r.to_dict() for r in results]

    async def search_twitter(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search Twitter. Uses bird CLI if available, else Exa."""
        ch = get_channel("twitter")
        results = await ch.search(query, config=self.config, limit=limit)
        return [r.to_dict() for r in results]

    async def search_youtube(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search YouTube via yt-dlp."""
        ch = get_channel("youtube")
        results = await ch.search(query, config=self.config, limit=limit)
        return [r.to_dict() for r in results]

    async def search_bilibili(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search Bilibili. Tries yt-dlp first, falls back to Exa."""
        ch = get_channel("bilibili")
        results = await ch.search(query, config=self.config, limit=limit)
        return [r.to_dict() for r in results]

    async def search_xhs(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search XiaoHongShu via mcporter."""
        ch = get_channel("xiaohongshu")
        results = await ch.search(query, config=self.config, limit=limit)
        return [r.to_dict() for r in results]

    # ── Health ──────────────────────────────────────────

    def doctor(self) -> Dict[str, dict]:
        """Check all channel availability."""
        from agent_reach.doctor import check_all
        return check_all(self.config)

    def doctor_report(self) -> str:
        """Get formatted health report."""
        from agent_reach.doctor import check_all, format_report
        return format_report(check_all(self.config))

    # ── Sync wrappers ───────────────────────────────────

    def read_sync(self, url: str) -> Dict[str, Any]:
        """Synchronous version of read()."""
        return asyncio.run(self.read(url))

    def search_sync(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """Synchronous version of search()."""
        return asyncio.run(self.search(query, num_results))

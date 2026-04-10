# -*- coding: utf-8 -*-
"""External-facing collection adapters."""

from __future__ import annotations

from typing import Type

from agent_reach.config import Config

from .base import BaseAdapter
from .bluesky import BlueskyAdapter
from .crawl4ai import Crawl4AIAdapter
from .exa_search import ExaSearchAdapter
from .github import GitHubAdapter
from .hacker_news import HackerNewsAdapter
from .hatena_bookmark import HatenaBookmarkAdapter
from .mcp_registry import MCPRegistryAdapter
from .qiita import QiitaAdapter
from .reddit import RedditAdapter
from .rss import RSSAdapter
from .searxng import SearXNGAdapter
from .twitter import TwitterAdapter
from .web import WebAdapter
from .youtube import YouTubeAdapter

ADAPTERS: dict[str, Type[BaseAdapter]] = {
    "bluesky": BlueskyAdapter,
    "crawl4ai": Crawl4AIAdapter,
    "web": WebAdapter,
    "exa_search": ExaSearchAdapter,
    "github": GitHubAdapter,
    "hatena_bookmark": HatenaBookmarkAdapter,
    "hacker_news": HackerNewsAdapter,
    "mcp_registry": MCPRegistryAdapter,
    "qiita": QiitaAdapter,
    "reddit": RedditAdapter,
    "youtube": YouTubeAdapter,
    "rss": RSSAdapter,
    "searxng": SearXNGAdapter,
    "twitter": TwitterAdapter,
}


def get_adapter(name: str, config: Config | None = None) -> BaseAdapter | None:
    """Return a configured adapter for the requested channel."""

    adapter_cls = ADAPTERS.get(name)
    if adapter_cls is None:
        return None
    return adapter_cls(config=config)


__all__ = [
    "ADAPTERS",
    "BaseAdapter",
    "BlueskyAdapter",
    "Crawl4AIAdapter",
    "ExaSearchAdapter",
    "GitHubAdapter",
    "HatenaBookmarkAdapter",
    "HackerNewsAdapter",
    "MCPRegistryAdapter",
    "QiitaAdapter",
    "RedditAdapter",
    "RSSAdapter",
    "SearXNGAdapter",
    "TwitterAdapter",
    "WebAdapter",
    "YouTubeAdapter",
    "get_adapter",
]

# -*- coding: utf-8 -*-
"""
Channel registry — lists all supported platforms for doctor checks.
"""

from typing import List, Optional
from .base import Channel

# Import all channels
from .web import WebChannel
from .github import GitHubChannel
from .twitter import TwitterChannel
from .youtube import YouTubeChannel
from .reddit import RedditChannel
from .rss import RSSChannel
from .bilibili import BilibiliChannel
from .exa_search import ExaSearchChannel
from .xiaohongshu import XiaoHongShuChannel
from .linkedin import LinkedInChannel
from .xiaoyuzhou import XiaoyuzhouChannel
from .v2ex import V2EXChannel
from .xueqiu import XueqiuChannel
from .arxiv import ArxivChannel
from .semantic_scholar import SemanticScholarChannel
from .research import ResearchChannel
from .openalex import OpenAlexChannel
from .pubmed import PubMedChannel
from .dblp import DBLPChannel
from .core_search import COREChannel
from .papers_with_code import PapersWithCodeChannel


ALL_CHANNELS: List[Channel] = [
    GitHubChannel(),
    TwitterChannel(),
    YouTubeChannel(),
    RedditChannel(),
    BilibiliChannel(),
    XiaoHongShuChannel(),
    LinkedInChannel(),
    XiaoyuzhouChannel(),
    V2EXChannel(),
    XueqiuChannel(),
    RSSChannel(),
    ExaSearchChannel(),
    WebChannel(),
    ArxivChannel(),
    SemanticScholarChannel(),
    ResearchChannel(),
    OpenAlexChannel(),
    PubMedChannel(),
    DBLPChannel(),
    COREChannel(),
    PapersWithCodeChannel(),
]


def get_channel(name: str) -> Optional[Channel]:
    """Get a channel by name."""
    for ch in ALL_CHANNELS:
        if ch.name == name:
            return ch
    return None


def get_all_channels() -> List[Channel]:
    """Get all registered channels."""
    return ALL_CHANNELS


__all__ = [
    "Channel",
    "ALL_CHANNELS",
    "get_channel", "get_all_channels",
]

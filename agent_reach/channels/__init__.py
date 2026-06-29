# -*- coding: utf-8 -*-
"""
Channel registry — lists all supported platforms for doctor checks.
"""

from typing import List, Optional

# Import all channels
from .base import Channel
from .bilibili import BilibiliChannel
from .exa_search import ExaSearchChannel
from .facebook import FacebookChannel
from .github import GitHubChannel
from .instagram import InstagramChannel
from .linkedin import LinkedInChannel
from .reddit import RedditChannel
from .rss import RSSChannel
from .twitter import TwitterChannel
from .v2ex import V2EXChannel
from .web import WebChannel
from .xiaohongshu import XiaoHongShuChannel
from .xiaoyuzhou import XiaoyuzhouChannel
from .xueqiu import XueqiuChannel
from .tiktok import TikTokChannel
from .youtube import YouTubeChannel

ALL_CHANNELS: List[Channel] = [
    GitHubChannel(),
    TwitterChannel(),
    YouTubeChannel(),
    RedditChannel(),
    FacebookChannel(),
    InstagramChannel(),
    TikTokChannel(),
    BilibiliChannel(),
    XiaoHongShuChannel(),
    LinkedInChannel(),
    XiaoyuzhouChannel(),
    V2EXChannel(),
    XueqiuChannel(),
    RSSChannel(),
    ExaSearchChannel(),
    WebChannel(),
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
    "get_channel",
    "get_all_channels",
]

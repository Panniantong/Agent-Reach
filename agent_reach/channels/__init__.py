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
from .youtube import YouTubeChannel

ALL_CHANNELS: List[Channel] = [
    GitHubChannel(),
    TwitterChannel(),
    YouTubeChannel(),
    RedditChannel(),
    FacebookChannel(),
    InstagramChannel(),
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


def get_channel_for_url(url: str) -> Channel:
    """Route a URL to the channel that owns it.

    WebChannel.can_handle() is True for every URL, so it is skipped during
    matching and used as the fallback — otherwise its registry position would
    decide the answer. A channel whose can_handle() raises is skipped rather
    than allowed to break routing for every other platform.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url 不能为空")
    for ch in ALL_CHANNELS:
        if ch.name == "web":
            continue
        try:
            if ch.can_handle(url):
                return ch
        except Exception:  # noqa: BLE001 — one bad matcher must not break routing
            continue
    return get_channel("web")


__all__ = [
    "Channel",
    "ALL_CHANNELS",
    "get_channel",
    "get_all_channels",
    "get_channel_for_url",
]

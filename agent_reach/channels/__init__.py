# -*- coding: utf-8 -*-
"""Registry of channels supported by the Windows/Codex fork."""

from __future__ import annotations

from typing import List, Optional

from .base import Channel
from .exa_search import ExaSearchChannel
from .github import GitHubChannel
from .rss import RSSChannel
from .twitter import TwitterChannel
from .web import WebChannel
from .youtube import YouTubeChannel

ALL_CHANNELS: List[Channel] = [
    WebChannel(),
    ExaSearchChannel(),
    GitHubChannel(),
    YouTubeChannel(),
    RSSChannel(),
    TwitterChannel(),
]


def get_channel(name: str) -> Optional[Channel]:
    """Return a channel by its stable name."""

    for channel in ALL_CHANNELS:
        if channel.name == name:
            return channel
    return None


def get_all_channels() -> List[Channel]:
    """Return all registered channels."""

    return ALL_CHANNELS


__all__ = ["Channel", "ALL_CHANNELS", "get_channel", "get_all_channels"]

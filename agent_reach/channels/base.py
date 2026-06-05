# -*- coding: utf-8 -*-
"""
Channel base class — platform availability checking.

Each channel represents a platform (YouTube, Twitter, GitHub, etc.)
and provides:
  - can_handle(url) → does this URL belong to this platform?
  - check(config) → is the upstream tool installed and configured?

After installation, agents call upstream tools directly.
"""

import shutil
from abc import ABC, abstractmethod
from typing import List, Tuple


class Channel(ABC):
    """Base class for all channels."""

    name: str = ""                    # e.g. "youtube"
    description: str = ""             # e.g. "YouTube 视频和字幕" (Chinese)
    description_en: str = ""          # e.g. "YouTube videos and subtitles" (English)
    backends: List[str] = []          # e.g. ["yt-dlp"] — what upstream tool is used
    tier: int = 0                     # 0=zero-config, 1=needs free key, 2=needs setup

    @property
    def display_name(self) -> str:
        """Return the description in the preferred language."""
        from agent_reach.lang import use_english
        if use_english() and self.description_en:
            return self.description_en
        return self.description

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this channel can handle this URL."""
        ...

    def check(self, config=None) -> Tuple[str, str]:
        """
        Check if this channel's upstream tool is available.
        Returns (status, message) where status is 'ok'/'warn'/'off'/'error'.
        """
        from agent_reach.lang import use_english
        if use_english():
            return "ok", "built-in" if not self.backends else ", ".join(self.backends)
        return "ok", f"{'、'.join(self.backends) if self.backends else '内置'}"

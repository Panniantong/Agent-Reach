# -*- coding: utf-8 -*-
"""RSS channel checks."""

from __future__ import annotations

from .base import Channel


class RSSChannel(Channel):
    name = "rss"
    description = "RSS and Atom feeds"
    backends = ["feedparser"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        lowered = url.lower()
        return any(marker in lowered for marker in ["/feed", "/rss", ".xml", "atom"])

    def check(self, config=None):
        try:
            import feedparser  # noqa: F401
        except ImportError:
            return "off", "feedparser is missing. Install it with pip install feedparser"
        return "ok", "Ready to parse RSS and Atom feeds"

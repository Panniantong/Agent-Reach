# -*- coding: utf-8 -*-
"""RSS — check if feedparser is available."""

from .base import Channel


class RSSChannel(Channel):
    name = "rss"
    description = "RSS/Atom feeds"
    backends = ["feedparser"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return any(x in url.lower() for x in ["/feed", "/rss", ".xml", "atom"])

    def check(self, config=None):
        try:
            import feedparser
            return "ok", "Can read RSS/Atom feeds"
        except ImportError:
            return "off", "feedparser not installed. Install: pip install feedparser"

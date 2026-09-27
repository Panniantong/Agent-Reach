# -*- coding: utf-8 -*-
"""RSS — check if feedparser is available."""

from .base import Channel


class RSSChannel(Channel):
    name = "rss"
    description = "RSS/Atom feed"
    backends = ["feedparser"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return any(x in url.lower() for x in ["/feed", "/rss", ".xml", "atom"])

    def check(self, config=None):
        try:
            import feedparser  # noqa: F401
        except ImportError:
            self.active_backend = None
            return "off", "feedparser is not installed. Installation: pip install feedparser"
        except Exception as e:
            # Installed but crashed during import (half-installation/version conflict) → Reinstall recipe
            self.active_backend = None
            return "error", f"Feedparser import failed: {e}\n Fix: pip install --force-reinstall feedparser"
        self.active_backend = self.backends[0]
        return "ok", "Can read RSS/Atom feeds"

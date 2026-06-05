# -*- coding: utf-8 -*-
"""RSS — check if feedparser is available."""

from .base import Channel


class RSSChannel(Channel):
    name = "rss"
    description = "RSS/Atom 订阅源"
    description_en = "RSS/Atom feeds"
    backends = ["feedparser"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return any(x in url.lower() for x in ["/feed", "/rss", ".xml", "atom"])

    def check(self, config=None):
        from agent_reach.lang import use_english

        try:
            import feedparser
            if use_english():
                return "ok", "Can read RSS/Atom feeds"
            return "ok", "可读取 RSS/Atom 源"
        except ImportError:
            if use_english():
                return "off", "feedparser not installed. Install: pip install feedparser"
            return "off", "feedparser 未安装。安装：pip install feedparser"

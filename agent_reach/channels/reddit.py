# -*- coding: utf-8 -*-
"""Reddit — check if proxy and credentials are configured."""

import os
from .base import Channel


class RedditChannel(Channel):
    name = "reddit"
    description = "Reddit 帖子和评论"
    backends = ["JSON API", "Exa"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "reddit.com" in d or "redd.it" in d

    def check(self, config=None):
        proxy = (config.get("reddit_proxy") if config else None) or os.environ.get("REDDIT_PROXY")
        if proxy:
            return "ok", "代理已配置，可读取帖子。搜索走 Exa"
        return "warn", (
            "无代理。服务器 IP 可能被 Reddit 封锁。配置代理：\n"
            "  agent-reach configure proxy http://user:pass@ip:port"
        )

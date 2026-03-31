# -*- coding: utf-8 -*-
"""Reddit — search and read via rdt-cli (public-clis/rdt-cli)."""

import shutil
import subprocess
from .base import Channel


class RedditChannel(Channel):
    name = "reddit"
    description = "Reddit 帖子和评论"
    backends = ["rdt-cli", "Exa", "Tavily"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "reddit.com" in d or "redd.it" in d

    def check(self, config=None):
        rdt = shutil.which("rdt")
        if rdt:
            return "ok", (
                "rdt-cli 可用（搜索帖子、阅读全文、查看评论，无需登录）"
            )
        return "off", (
            "需要安装 rdt-cli：\n"
            "  pipx install rdt-cli\n"
            "或：\n"
            "  uv tool install rdt-cli\n"
            "搜索也可使用 Exa（免费）或 Tavily（需 API Key）作为替代"
        )

# -*- coding: utf-8 -*-
"""Instagram — check connectivity and configuration."""

import os
import urllib.request
from .base import Channel

_TIMEOUT = 10


def _instagram_reachable() -> bool:
    """Return True if Instagram is reachable."""
    url = "https://www.instagram.com/"
    req = urllib.request.Request(url, headers={"User-Agent": "agent-reach/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status == 200
    except Exception:
        return False


class InstagramChannel(Channel):
    name = "instagram"
    description = "Instagram 帖子和 Reels"
    backends = ["Instagram API"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "instagram.com" in d or "instagr.am" in d

    def check(self, config=None):
        token = (config.get("instagram_token") if config else None) or os.environ.get("INSTAGRAM_TOKEN")
        if not token:
            return "warn", (
                "未配置 Instagram Token。请设置环境变量：\n"
                "  export INSTAGRAM_TOKEN=your_access_token"
            )
        if _instagram_reachable():
            return "ok", "Instagram 可达，Token 已配置"
        return "warn", "Instagram 无法连接，请检查网络或代理配置"

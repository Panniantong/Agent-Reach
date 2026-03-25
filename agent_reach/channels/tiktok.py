# -*- coding: utf-8 -*-
"""TikTok — check connectivity and configuration."""

import os
import urllib.request
from .base import Channel

_TIMEOUT = 10


def _tiktok_reachable() -> bool:
    """Return True if TikTok is reachable."""
    url = "https://www.tiktok.com/"
    req = urllib.request.Request(url, headers={"User-Agent": "agent-reach/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status == 200
    except Exception:
        return False


class TikTokChannel(Channel):
    name = "tiktok"
    description = "TikTok 短视频和评论"
    backends = ["TikTok API"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "tiktok.com" in d or "vm.tiktok.com" in d

    def check(self, config=None):
        token = (config.get("tiktok_token") if config else None) or os.environ.get("TIKTOK_TOKEN")
        if not token:
            return "warn", (
                "未配置 TikTok Token。请设置环境变量：\n"
                "  export TIKTOK_TOKEN=your_access_token"
            )
        if _tiktok_reachable():
            return "ok", "TikTok 可达，Token 已配置"
        return "warn", "TikTok 无法连接，请检查网络或代理配置"

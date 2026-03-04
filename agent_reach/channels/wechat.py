# -*- coding: utf-8 -*-
"""WeChat Official Account articles — check if wechat-article-for-ai is available."""

import shutil
import subprocess
from .base import Channel


class WeChatChannel(Channel):
    name = "wechat"
    description = "微信公众号文章"
    backends = ["wechat-article-for-ai (Camoufox)"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "mp.weixin.qq.com" in d or "weixin.qq.com" in d

    def check(self, config=None):
        try:
            import camoufox  # noqa: F401
        except ImportError:
            return "off", (
                "需要 wechat-article-for-ai。安装：\n"
                "  pip install camoufox[geoip] markdownify beautifulsoup4 httpx mcp\n"
                "  # 或完整安装：\n"
                "  git clone https://github.com/bzd6661/wechat-article-for-ai.git\n"
                "  cd wechat-article-for-ai && pip install -r requirements.txt\n"
                "  详见 https://github.com/bzd6661/wechat-article-for-ai"
            )
        return "ok", "可读取微信公众号文章（URL → Markdown）"

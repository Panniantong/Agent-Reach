# -*- coding: utf-8 -*-
"""WeChat Official Account articles — read and search.

Read:   wechat-article-for-ai (Camoufox stealth browser)
Search: miku_ai (Sogou WeChat search)
"""

import shutil
import subprocess
from .base import Channel


class WeChatChannel(Channel):
    name = "wechat"
    description = "微信公众号文章"
    backends = ["wechat-article-for-ai (Camoufox)", "miku_ai (搜狗搜索)"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "mp.weixin.qq.com" in d or "weixin.qq.com" in d

    def check(self, config=None):
        has_read = False
        has_search = False

        try:
            import camoufox  # noqa: F401
            has_read = True
        except ImportError:
            pass

        try:
            import miku_ai  # noqa: F401
            has_search = True
        except ImportError:
            pass

        if has_read and has_search:
            return "ok", "完整可用（搜索 + 阅读公众号文章）"
        elif has_read:
            return "ok", "可阅读公众号文章（URL → Markdown）。安装 miku_ai 可解锁搜索：pip install miku_ai"
        elif has_search:
            return "warn", (
                "可搜索公众号文章但无法阅读全文。安装阅读工具：\n"
                "  pip install camoufox[geoip] markdownify beautifulsoup4 httpx mcp"
            )
        else:
            return "off", (
                "需要安装微信公众号工具：\n"
                "  # 阅读（URL → Markdown）：\n"
                "  pip install camoufox[geoip] markdownify beautifulsoup4 httpx mcp\n"
                "  # 搜索（关键词 → 文章列表）：\n"
                "  pip install miku_ai\n"
                "  详见 https://github.com/bzd6661/wechat-article-for-ai"
            )

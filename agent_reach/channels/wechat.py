# -*- coding: utf-8 -*-
"""WeChat Official Account articles — read and search.

Read:   Exa crawling (primary) / Camoufox stealth browser (optional)
Search: Exa web_search with includeDomains mp.weixin.qq.com
"""

import shutil
import subprocess
from .base import Channel


def _exa_available() -> bool:
    mcporter = shutil.which("mcporter")
    if not mcporter:
        return False
    try:
        r = subprocess.run(
            [mcporter, "config", "list"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=5,
        )
        return "exa" in r.stdout.lower()
    except Exception:
        return False


class WeChatChannel(Channel):
    name = "wechat"
    description = "微信公众号文章"
    description_en = "WeChat Official Account articles"
    backends = ["Exa via mcporter (search+read)", "Camoufox (optional read)"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "mp.weixin.qq.com" in d or "weixin.qq.com" in d

    def check(self, config=None):
        from agent_reach.lang import use_english

        has_exa = _exa_available()
        has_camoufox = False
        try:
            import camoufox  # noqa: F401
            has_camoufox = True
        except ImportError:
            pass

        if has_exa and has_camoufox:
            if use_english():
                return "ok", "Fully available (Exa search + Exa/Camoufox read WeChat articles)"
            return "ok", "完整可用（Exa 搜索 + Exa/Camoufox 阅读公众号文章）"
        elif has_exa:
            if use_english():
                return "ok", (
                    "Search and read WeChat Official Account articles via Exa (free, no config needed). "
                    "Optionally install Camoufox for better full-text reading."
                )
            return "ok", (
                "通过 Exa 搜索和阅读微信公众号文章（免费，无需额外配置）。"
                "可选安装 Camoufox 获得更好的全文阅读效果。"
            )
        elif has_camoufox:
            if use_english():
                return "warn", (
                    "Camoufox can read articles, but search requires Exa. "
                    "Run `agent-reach install --env=auto` to install Exa."
                )
            return "warn", (
                "Camoufox 可阅读公众号文章，但搜索功能需要 Exa。"
                "运行 `agent-reach install --env=auto` 安装 Exa。"
            )
        else:
            if use_english():
                return "off", (
                    "mcporter + Exa MCP required to search and read WeChat articles.\n"
                    "Run `agent-reach install --env=auto` to install."
                )
            return "off", (
                "需要 mcporter + Exa MCP 来搜索和阅读微信公众号文章。\n"
                "运行 `agent-reach install --env=auto` 安装。"
            )

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
    description = "WeChat Official Account articles"
    backends = ["Exa via mcporter (search + read)", "Camoufox (optional read)"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "mp.weixin.qq.com" in d or "weixin.qq.com" in d

    def check(self, config=None):
        has_exa = _exa_available()
        has_camoufox = False
        try:
            import camoufox  # noqa: F401
            has_camoufox = True
        except ImportError:
            pass

        if has_exa and has_camoufox:
            return "ok", "Fully available (Exa search + Exa/Camoufox reading of Official Account articles)"
        elif has_exa:
            return "ok", (
                "Search and read WeChat Official Account articles via Exa (free, no extra configuration). "
                "Optionally install Camoufox for better full-text reading."
            )
        elif has_camoufox:
            return "warn", (
                "Camoufox can read Official Account articles, but search requires Exa. "
                "Run `agent-reach install --env=auto` to install Exa."
            )
        else:
            return "off", (
                "mcporter + Exa MCP required to search and read WeChat Official Account articles.\n"
                "Run `agent-reach install --env=auto` to install."
            )

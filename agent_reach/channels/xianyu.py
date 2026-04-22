# -*- coding: utf-8 -*-
"""Xianyu (闲鱼) — second-hand market items.

Read:   Jina Reader (primary)
Search: Exa via mcporter (optional)
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
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        return "exa" in r.stdout.lower()
    except Exception:
        return False


class XianyuChannel(Channel):
    name = "xianyu"
    description = "闲鱼二手商品"
    backends = ["Jina Reader (阅读)", "Exa (搜索, 可选)"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return (
            "goofish.com" in d
            or "2.taobao.com" in d
            or "xy.taobao.com" in d
            or "m.tb.cn" in d
            or "taobao.com" in d
            and ("fleamarket" in url or "idleFish" in url)
        )

    def check(self, config=None):
        has_exa = _exa_available()

        if has_exa:
            return "ok", "通过 Jina Reader 读取商品，通过 Exa MCP 搜索商品（完整可用）。"
        else:
            return "warn", (
                "通过 Jina Reader 可读取闲鱼商品。\n"
                "如需搜索闲鱼商品，请安装 Exa MCP：运行 `agent-reach install --env=auto`"
            )

# -*- coding: utf-8 -*-
"""Boss直聘 — check if mcp-bosszp is available."""

import shutil
import subprocess
from .base import Channel


class BossZhipinChannel(Channel):
    name = "bosszhipin"
    description = "Boss直聘职位搜索"
    backends = ["mcp-bosszp", "Jina Reader"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        return "zhipin.com" in domain or "boss.com" in domain

    def check(self, config=None):
        if not shutil.which("mcporter"):
            return "off", (
                "可通过 Jina Reader 读取职位页面。完整功能需要：\n"
                "  1. git clone https://github.com/mucsbr/mcp-bosszp.git\n"
                "  2. cd mcp-bosszp && pip install -r requirements.txt && playwright install chromium\n"
                "  3. python boss_zhipin_fastmcp_v2.py（启动后扫码登录）\n"
                "  4. mcporter config add bosszhipin http://localhost:8000/mcp"
            )
        try:
            r = subprocess.run(
                ["mcporter", "list"], capture_output=True, text=True, timeout=10
            )
            out = r.stdout.lower()
            if "boss" in out or "zhipin" in out:
                return "ok", "可搜索职位、向 HR 打招呼"
        except Exception:
            pass
        return "off", (
            "mcporter 已装但 Boss直聘 MCP 未配置。\n"
            "  详见 https://github.com/mucsbr/mcp-bosszp"
        )

# -*- coding: utf-8 -*-
"""LinkedIn — check if linkedin-scraper-mcp is available."""

import shutil
import subprocess
from .base import Channel


class LinkedInChannel(Channel):
    name = "linkedin"
    description = "LinkedIn 职业社交"
    backends = ["linkedin-scraper-mcp", "Jina Reader"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        return "linkedin.com" in urlparse(url).netloc.lower()

    def check(self, config=None):
        if not shutil.which("mcporter"):
            return "off", (
                "基本内容可通过 Jina Reader 读取。完整功能需要：\n"
                "  pip install linkedin-scraper-mcp\n"
                "  mcporter config add linkedin http://localhost:3000/mcp\n"
                "  详见 https://github.com/stickerdaniel/linkedin-mcp-server"
            )
        try:
            r = subprocess.run(
                ["mcporter", "list"], capture_output=True, text=True, timeout=10
            )
            if "linkedin" in r.stdout.lower():
                return "ok", "完整可用（Profile、公司、职位搜索）"
        except Exception:
            pass
        return "off", (
            "mcporter 已装但 LinkedIn MCP 未配置。运行：\n"
            "  pip install linkedin-scraper-mcp\n"
            "  mcporter config add linkedin http://localhost:3000/mcp"
        )

# -*- coding: utf-8 -*-
"""LinkedIn — check if linkedin-scraper-mcp is available."""

import shutil
import subprocess
from .base import Channel


class LinkedInChannel(Channel):
    name = "linkedin"
    description = "LinkedIn 职业社交"
    description_en = "LinkedIn professional network"
    backends = ["linkedin-scraper-mcp", "Jina Reader"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        return "linkedin.com" in urlparse(url).netloc.lower()

    def check(self, config=None):
        from agent_reach.lang import use_english

        mcporter = shutil.which("mcporter")
        if not mcporter:
            if use_english():
                return "off", (
                    "Basic content readable via Jina Reader. Full features require:\n"
                    "  pip install linkedin-scraper-mcp\n"
                    "  mcporter config add linkedin http://localhost:3000/mcp\n"
                    "  See https://github.com/stickerdaniel/linkedin-mcp-server"
                )
            return "off", (
                "基本内容可通过 Jina Reader 读取。完整功能需要：\n"
                "  pip install linkedin-scraper-mcp\n"
                "  mcporter config add linkedin http://localhost:3000/mcp\n"
                "  详见 https://github.com/stickerdaniel/linkedin-mcp-server"
            )
        try:
            r = subprocess.run(
                [mcporter, "config", "list"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            if "linkedin" in r.stdout.lower():
                if use_english():
                    return "ok", "Fully available (Profile, company, job search)"
                return "ok", "完整可用（Profile、公司、职位搜索）"
        except Exception:
            pass
        if use_english():
            return "off", (
                "mcporter installed but LinkedIn MCP not configured. Run:\n"
                "  pip install linkedin-scraper-mcp\n"
                "  mcporter config add linkedin http://localhost:3000/mcp"
            )
        return "off", (
            "mcporter 已装但 LinkedIn MCP 未配置。运行：\n"
            "  pip install linkedin-scraper-mcp\n"
            "  mcporter config add linkedin http://localhost:3000/mcp"
        )

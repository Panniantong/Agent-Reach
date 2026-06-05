# -*- coding: utf-8 -*-
"""LinkedIn — check if linkedin-scraper-mcp is available."""

import shutil
import subprocess
from .base import Channel


class LinkedInChannel(Channel):
    name = "linkedin"
    description = "LinkedIn professional network"
    backends = ["linkedin-scraper-mcp", "Jina Reader"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        return "linkedin.com" in urlparse(url).netloc.lower()

    def check(self, config=None):
        mcporter = shutil.which("mcporter")
        if not mcporter:
            return "off", (
                "Basic content can be read via Jina Reader. Full functionality requires:\n"
                "  pip install linkedin-scraper-mcp\n"
                "  mcporter config add linkedin http://localhost:3000/mcp\n"
                "  See https://github.com/stickerdaniel/linkedin-mcp-server"
            )
        try:
            r = subprocess.run(
                [mcporter, "config", "list"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            if "linkedin" in r.stdout.lower():
                return "ok", "Fully available (profile, company, job search)"
        except Exception:
            pass
        return "off", (
            "mcporter installed but LinkedIn MCP not configured. Run:\n"
            "  pip install linkedin-scraper-mcp\n"
            "  mcporter config add linkedin http://localhost:3000/mcp"
        )

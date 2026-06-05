# -*- coding: utf-8 -*-
"""Exa Search — check if mcporter + Exa MCP is available."""

import shutil
import subprocess
from .base import Channel


class ExaSearchChannel(Channel):
    name = "exa_search"
    description = "Web-wide semantic search"
    backends = ["Exa via mcporter"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def check(self, config=None):
        mcporter = shutil.which("mcporter")
        if not mcporter:
            return "off", (
                "mcporter + Exa MCP required. Install:\n"
                "  npm install -g mcporter\n"
                "  mcporter config add exa https://mcp.exa.ai/mcp"
            )
        try:
            r = subprocess.run(
                [mcporter, "config", "list"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            if "exa" in r.stdout.lower():
                return "ok", "Web-wide semantic search available (free, no API Key required)"
            return "off", (
                "mcporter installed but Exa not configured. Run:\n"
                "  mcporter config add exa https://mcp.exa.ai/mcp"
            )
        except Exception:
            return "off", "mcporter connection error"

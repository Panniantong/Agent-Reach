# -*- coding: utf-8 -*-
"""Exa search channel checks."""

from __future__ import annotations

import subprocess

from agent_reach.utils.commands import find_command
from agent_reach.utils.paths import get_mcporter_config_path, render_mcporter_command

from .base import Channel

EXA_SERVER_URL = "https://mcp.exa.ai/mcp"


class ExaSearchChannel(Channel):
    name = "exa_search"
    description = "Cross-web search via Exa"
    backends = ["mcporter", "Exa MCP"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return False

    def check(self, config=None):
        mcporter = find_command("mcporter")
        if not mcporter:
            return "off", (
                "mcporter is missing. Install it with npm install -g mcporter"
            )
        try:
            config_path = get_mcporter_config_path()
            result = subprocess.run(
                [mcporter, "--config", str(config_path), "config", "list"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except Exception:
            return "off", "mcporter is installed but its config could not be read"

        if "exa" in (result.stdout or "").lower():
            return "ok", "Ready for Exa web search without an API key"
        return "off", (
            "Exa is not configured. Run "
            + render_mcporter_command(f"config add exa {EXA_SERVER_URL}")
        )

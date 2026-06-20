# -*- coding: utf-8 -*-
"""Exa Search — check if mcporter + Exa MCP is available."""

from agent_reach.probe import probe_command

from .base import Channel

#: mcporter is npm package, broken hint differs from default pipx/uv
_MCPORTER_BROKEN_HINT = "mcporter can't execute (node environment broken), reinstall:\n  npm install -g mcporter"


class ExaSearchChannel(Channel):
    name = "exa_search"
    description = "Semantic web search"
    backends = ["Exa via mcporter"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def check(self, config=None):
        self.active_backend = None
        probe = probe_command("mcporter", ["config", "list"], timeout=10, package="mcporter")
        if probe.status == "missing":
            return "off", (
                "mcporter + Exa MCP required. Install:\n"
                "  npm install -g mcporter\n"
                "  mcporter config add exa https://mcp.exa.ai/mcp"
            )
        if probe.status == "broken":
            return "error", _MCPORTER_BROKEN_HINT
        if not probe.ok:  # timeout / error
            return "error", f"mcporter execution error: {probe.hint or probe.output or probe.status}"
        if "exa" in probe.output.lower():
            self.active_backend = self.backends[0]
            return "ok", "Semantic web search available (free, no API key required)"
        return "off", (
            "mcporter installed but Exa not configured. Run:\n"
            "  mcporter config add exa https://mcp.exa.ai/mcp"
        )

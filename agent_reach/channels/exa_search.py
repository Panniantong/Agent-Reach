# -*- coding: utf-8 -*-
"""Exa Search — check if mcporter + Exa MCP is available."""

import shutil

from .base import Channel
from .mcporter import McporterConfigError, inspect_mcporter_config


class ExaSearchChannel(Channel):
    name = "exa_search"
    description = "Web-wide semantic search"
    backends = ["Exa via mcporter"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def check(self, config=None):
        self.active_backend = None
        if not shutil.which("mcporter"):
            return "off", (
                "Requires mcporter + Exa MCP. Installation: \n"
                "  npm install -g mcporter\n"
                "  mcporter config add exa https://mcp.exa.ai/mcp --scope home"
            )
        try:
            inspection = inspect_mcporter_config()
        except McporterConfigError as exc:
            return "error", f"mcporter configuration check failed: {exc}"
        if "exa" in inspection.server_names:
            return "warn", (
                "Exa is configured in mcporter, but Doctor has not started a connection to the remote service. "
                "Configuration alone does not prove availability; connectivity is unverified."
            )
        if inspection.imports_unchecked:
            return "warn", (
                "Exa is not found in the mcporter local configuration; the configuration also has editor imports enabled, "
                "Doctor does not expand them to avoid reading additional credentials; access is unverified."
            )
        return "off", (
            "mcporter is installed but Exa is not configured. Run: \n"
            "  mcporter config add exa https://mcp.exa.ai/mcp --scope home"
        )

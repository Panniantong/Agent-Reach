# -*- coding: utf-8 -*-
"""LinkedIn — check if mcp-server-linkedin is configured."""

import shutil

from .base import Channel
from .mcporter import McporterConfigError, inspect_mcporter_config

_LINKEDIN_SERVER_NAMES = {
    "linkedin",
    "linkedin-scraper",
    "linkedin-scraper-mcp",
    "mcp-server-linkedin",
}
_LOGIN_COMMAND = "uvx mcp-server-linkedin@latest --login"
_UV_INSTALL_URL = "https://docs.astral.sh/uv/getting-started/installation/"
_CONFIG_COMMAND = (
    "mcporter config add linkedin --command uvx "
    "--arg mcp-server-linkedin@latest --env UV_HTTP_TIMEOUT=300 --scope home"
)


class LinkedInChannel(Channel):
    name = "linkedin"
    description = "LinkedIn professional networking"
    backends = ["mcp-server-linkedin", "Jina Reader"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "linkedin.com")

    def check(self, config=None):
        self.active_backend = None
        if not shutil.which("mcporter"):
            return "off", (
                "Basic content can be read through Jina Reader. Full functionality requires: \n"
                f"  Install uv/uvx first: {_UV_INSTALL_URL}\n"
                f"  {_LOGIN_COMMAND}\n"
                f"  {_CONFIG_COMMAND}\n"
                "  See https://github.com/stickerdaniel/linkedin-mcp-server for details"
            )
        try:
            inspection = inspect_mcporter_config()
        except McporterConfigError as exc:
            return "error", f"mcporter configuration check failed: {exc}"
        if inspection.server_names & _LINKEDIN_SERVER_NAMES:
            if not shutil.which("uvx"):
                return "warn", (
                    "LinkedIn MCP is configured in mcporter, but uvx is not installed. "
                    "The service cannot start. Install: \n"
                    f"  {_UV_INSTALL_URL}"
                )
            return "warn", (
                "LinkedIn MCP is configured in mcporter, but Doctor has not started the local "
                "service to verify connectivity. Configuration alone does not prove availability."
            )
        if inspection.imports_unchecked:
            return "warn", (
                "LinkedIn MCP is absent from local mcporter configuration. Editor imports are enabled, "
                "but Doctor does not expand them to avoid reading additional credentials; access is unverified."
            )
        return "off", (
            "mcporter is installed but LinkedIn MCP is not configured. Run: \n"
            f"  Install uv/uvx first: {_UV_INSTALL_URL}\n"
            f"  {_LOGIN_COMMAND}\n"
            f"  {_CONFIG_COMMAND}"
        )

# -*- coding: utf-8 -*-
"""Shared channel helper for OpenCLI browser-session-only platforms."""

from urllib.parse import urlparse

from .base import Channel


class OpenCLISiteChannel(Channel):
    """A platform served directly by OpenCLI.

    These channels are intentionally thin: Agent Reach only installs,
    health-checks, and routes. Agents call `opencli <site> ...` directly.
    """

    site: str = ""
    domains: tuple[str, ...] = ()
    usage: str = ""
    login_hint: str = ""

    backends = ["OpenCLI"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        domain = urlparse(url).netloc.lower()
        return any(domain == d or domain.endswith(f".{d}") for d in self.domains)

    def check(self, config=None):
        from agent_reach.backends import opencli_status

        self.active_backend = None
        st = opencli_status()
        if not st.installed:
            return "off", (
                f"{self.description} backend not installed. Install:\n"
                "  agent-reach install --channels opencli\n"
                f"then log into {self.login_hint} in Chrome"
            )
        if st.broken:
            return "error", st.hint

        self.active_backend = "OpenCLI"
        if st.ready:
            return "ok", (
                f"OpenCLI available (reuses browser login session). Usage: {self.usage}. "
                f"If it asks you to log in, log into {self.login_hint} in Chrome first"
            )
        return "warn", st.hint

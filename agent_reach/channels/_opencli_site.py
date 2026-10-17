# -*- coding: utf-8 -*-
"""Shared channel helper for OpenCLI browser-session-only platforms."""

from agent_reach.backends.opencli import opencli_call, opencli_items
from agent_reach.runtime.result import NOT_FOUND, UPSTREAM_BROKEN, ReachError
from agent_reach.utils.url import host_matches

from .base import Channel


class OpenCLISiteChannel(Channel):
    """A platform served only through OpenCLI in the Agent Reach browser."""

    site: str = ""
    domains: tuple[str, ...] = ()
    usage: str = ""
    login_hint: str = ""

    tools = ("opencli",)
    prereqs = ("node", "chrome")

    def setup_problems(self):
        from agent_reach.runtime.browser_binding import setup_problems

        return setup_problems(self.name)

    def can_handle(self, url: str) -> bool:
        return host_matches(url, *self.domains)

    # ── unified entry helper ──

    def _opencli(self, args, timeout: float, *, empty_is_error: bool = True) -> list:
        """Run one OpenCLI command for this site and return unified items."""
        hint = (
            f"Run `agent-reach login {self.name}` and ask the user to log in to {self.login_hint} "
            "in the Agent Reach browser window it opens. Never log in for them."
        )
        items = opencli_items(opencli_call(self.site, list(args), timeout=timeout, login_hint=hint))
        if not items:
            if empty_is_error:
                raise ReachError(UPSTREAM_BROKEN, "OpenCLI returned nothing; the page most likely did not load")
            raise ReachError(NOT_FOUND, "nothing found")
        return items

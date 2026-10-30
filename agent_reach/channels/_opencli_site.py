# -*- coding: utf-8 -*-
"""Shared channel helper for OpenCLI browser-session-only platforms."""

from agent_reach.backends.opencli import opencli_call, opencli_items
from agent_reach.runtime.result import NEED_LOGIN, NOT_FOUND, UPSTREAM_BROKEN, ReachError
from agent_reach.utils.url import host_matches

from .base import Channel


class OpenCLISiteChannel(Channel):
    """A platform served only through OpenCLI in the Agent Reach browser."""

    site: str = ""
    domains: tuple[str, ...] = ()
    usage: str = ""
    login_hint: str = ""
    #: Cookie the site sets only for a logged-in user; its absence turns an unclear failure into NEED_LOGIN.
    login_cookie: str = ""

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
        try:
            items = opencli_items(opencli_call(self.site, list(args), timeout=timeout, login_hint=hint))
            if not items and empty_is_error:
                raise ReachError(UPSTREAM_BROKEN, "OpenCLI finished but returned no items")
        except ReachError as err:
            if err.code == UPSTREAM_BROKEN and self._logged_out():
                raise ReachError(NEED_LOGIN, f"Not logged in to {self.login_hint}", hint=hint) from None
            raise
        if not items:
            raise ReachError(NOT_FOUND, "nothing found")
        return items

    def _logged_out(self) -> bool:
        """True only when the dedicated browser is running and lacks this site's login cookie."""
        if not self.login_cookie:
            return False
        from agent_reach.runtime import browser, cdp
        if not browser.is_running():
            return False
        return not any(c.get("name") == self.login_cookie for d in self.domains for c in cdp.cookies(d))

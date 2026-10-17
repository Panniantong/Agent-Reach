# -*- coding: utf-8 -*-
"""XiaoHongShu — OpenCLI in the Agent Reach browser."""

from agent_reach.backends.opencli import opencli_call, opencli_items
from agent_reach.runtime.result import BAD_INPUT, NOT_FOUND, UPSTREAM_BROKEN, ReachError

from .base import Action, Channel, Param

_XHS_LOGIN_HINT = (
    "Ask the user to log in to xiaohongshu.com in their own Chrome (the one with "
    "the OpenCLI extension). Never log in or read browser cookies for them."
)


class XiaoHongShuChannel(Channel):
    name = "xiaohongshu"
    description = "小红书笔记"

    level = "optional"
    login_url = "https://www.xiaohongshu.com/explore"
    tools = ("opencli",)
    prereqs = ("node", "chrome")

    def setup_problems(self):
        from agent_reach.runtime.browser_binding import setup_problems

        return setup_problems(self.name)

    actions = (
        Action(
            "search",
            "Search notes",
            (
                Param("query", "what to search for"),
                Param("limit", "max results", required=False, type=int, default=5),
            ),
            (("cloakbrowser", "_cloak_search"), ("opencli", "_opencli_search")),
            live_test={"query": "咖啡", "limit": 2},
        ),
        Action(
            "read",
            "Read a note (full link including xsec_token, as returned by search)",
            (Param("target", "full note link with xsec_token"),),
            (("cloakbrowser", "_cloak_read"), ("opencli", "_opencli_read")),
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "xiaohongshu.com", "xhslink.com")

    # ── unified entry backends ──

    def _opencli_search(self, *, query: str, limit: int, timeout: float) -> list:
        rows = opencli_call(
            "xiaohongshu", ["search", query, "--limit", str(limit)],
            timeout=timeout, login_hint=_XHS_LOGIN_HINT,
        )
        items = opencli_items(rows)[:limit]
        if not items:
            raise ReachError(
                UPSTREAM_BROKEN,
                "OpenCLI returned no notes; the page most likely did not load",
            )
        return items

    def _opencli_read(self, *, target: str, timeout: float) -> list:
        from agent_reach.utils.url import host_matches

        url = str(target).strip()
        if not host_matches(url, "xiaohongshu.com", "xhslink.com"):
            raise ReachError(BAD_INPUT, "target must be a full Xiaohongshu note link including xsec_token")
        rows = opencli_call("xiaohongshu", ["note", url], timeout=timeout, login_hint=_XHS_LOGIN_HINT)
        if isinstance(rows, list) and rows and all(isinstance(r, dict) and "field" in r and "value" in r for r in rows):
            note = {r["field"]: r["value"] for r in rows}
            note["url"] = url
            rows = [note]
        items = opencli_items(rows)
        if not items:
            raise ReachError(NOT_FOUND, "note not found")
        return items[:1]

    def _cloak_search(self, *, query, limit, timeout):
        from agent_reach.backends.cloak import call
        return call(self.name, "search", query=query, limit=limit, timeout=timeout)

    def _cloak_read(self, *, target, timeout):
        from agent_reach.backends.cloak import call
        return call(self.name, "read", target=target, timeout=timeout)

    def on_remove(self):
        from agent_reach.backends.cloak import logout
        logout(self.name)

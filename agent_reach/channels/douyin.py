# -*- coding: utf-8 -*-
"""Douyin (抖音) through upstream OpenCLI in the Reach-owned browser.

Douyin renders its result cards only inside a visible window and refuses to
paint them in a headless one, so this channel makes sure a dated window is open
before asking OpenCLI for the cards. The login lives in the Reach profile; the
user logs in there themselves.
"""

from agent_reach.backends.opencli import opencli_call, opencli_items
from agent_reach.runtime.result import BAD_INPUT, UPSTREAM_BROKEN, ReachError

from .base import Action, Channel, Param

MAX_LIMIT = 30
PUBLISH_WINDOWS = (0, 1, 7, 182, 365)

_DOUYIN_LOGIN_HINT = (
    "Run agent-reach login douyin to open the Agent Reach dedicated browser. "
    "Reach keeps the site login in its own profile; the user completes any remaining login. "
    "Never ask for a password."
)


def _open_window() -> None:
    """Douyin paints results only in a headed window.

    `browser.start()` opens the same saved profile visibly, does nothing when a
    visible window is already up, and replaces a headless one.
    """
    from agent_reach.runtime import browser

    browser.start("https://www.douyin.com/")


def _first_line(text: str, limit: int = 60) -> str:
    head = " ".join((text or "").split())
    return head if len(head) <= limit else head[:limit] + "…"


def _publish_time_unsupported(exc: ReachError) -> bool:
    """True when this OpenCLI build does not know the `--publish-time` flag yet."""
    message = str(getattr(exc, "message", "") or "").lower()
    return "--publish-time" in message or "unknown option" in message


class DouyinChannel(Channel):
    name = "douyin"
    description = "抖音视频"

    level = "optional"
    login_url = "https://www.douyin.com/"
    domains = ("douyin.com",)
    tools = ("opencli",)
    prereqs = ("node", "chrome")

    def setup_problems(self):
        from agent_reach.runtime.browser_binding import setup_problems

        return setup_problems(self.name)

    actions = (
        Action(
            "search",
            "Search videos (opens a visible browser window; Douyin does not paint results headless)",
            (
                Param("query", "what to search for"),
                Param("limit", "max results", required=False, type=int, default=10),
                Param("days", "only videos from the last N days: 0 (any), 1, 7, 182 or 365",
                      required=False, type=int, default=0),
            ),
            (("opencli", "_opencli_search"),),
            live_test={"query": "咖啡", "limit": 2},
            timeout=150,
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "douyin.com", "iesdouyin.com")

    def validate_params(self, action, params):
        if action != "search":
            return
        if params["days"] not in PUBLISH_WINDOWS:
            raise ReachError(
                BAD_INPUT,
                "days must be 0, 1, 7, 182 or 365 — Douyin offers only those publish windows",
            )
        if not 1 <= params["limit"] <= MAX_LIMIT:
            raise ReachError(BAD_INPUT, f"limit must be between 1 and {MAX_LIMIT}")

    def _opencli_search(self, *, query: str, limit: int, days: int, timeout: float) -> list:
        _open_window()
        args = ["search", query, "--limit", str(limit)]
        if days:
            args += ["--publish-time", str(days)]
        try:
            rows = opencli_call("douyin", args, timeout=timeout, login_hint=_DOUYIN_LOGIN_HINT)
        except ReachError as exc:
            if days and _publish_time_unsupported(exc):
                raise ReachError(
                    BAD_INPUT,
                    "this site tool cannot filter by publish time yet",
                    hint="Search again without --days, or update the site tool when it supports --publish-time.",
                ) from None
            raise
        items = opencli_items(rows)[:limit]
        for item in items:
            text = (item.get("text") or "").strip()
            if not item.get("title"):
                item["title"] = _first_line(text) or None
        if not items:
            raise ReachError(
                UPSTREAM_BROKEN,
                "the site tool finished but returned no video cards",
            )
        return items

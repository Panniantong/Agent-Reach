# -*- coding: utf-8 -*-
"""XiaoHongShu through upstream OpenCLI in the Reach-owned browser.

Accounts outside mainland China are redirected from xiaohongshu.com to the
international mirror rednote.com, so their login lives on that domain only.
The channel serves both: search tries the site that last worked first and moves
to the other one only on NEED_LOGIN; note links go to their own site first.
"""

import time

from agent_reach.backends.opencli import opencli_call, opencli_items
from agent_reach.runtime.result import BAD_INPUT, NEED_LOGIN, NOT_FOUND, UPSTREAM_BROKEN, ReachError

from .base import Action, Channel, Param

_XHS_LOGIN_HINT = (
    "Run agent-reach login xiaohongshu to open the Agent Reach dedicated browser. "
    "Reach first tries the existing local site login; the user completes any remaining login. Never ask for a password."
)

# OpenCLI site name -> web host. "rednote" is OpenCLI's adapter for the international mirror.
_SITE_HOSTS = {"xiaohongshu": "www.xiaohongshu.com", "rednote": "www.rednote.com"}
_NOTE_HOSTS = ("xiaohongshu.com", "rednote.com")
# Same-platform searches stay BROWSER_SEARCH_INTERVAL apart, also across the two domains.
_FALLBACK_GAP_S = 10.0
# Least time a second search needs after the gap; below that, report the login error instead.
_MIN_ATTEMPT_S = 5.0


def _other(site: str) -> str:
    return "xiaohongshu" if site == "rednote" else "rednote"


def _saved_site() -> str:
    from agent_reach.runtime import state

    record = state.load()["channels"].get("xiaohongshu")
    site = record.get("site") if isinstance(record, dict) else None
    return site if site in _SITE_HOSTS else "xiaohongshu"


def _remember_site(site: str) -> None:
    """Store the site that worked in the channel record, so `remove` clears it too."""
    from agent_reach.runtime import state

    def change(data):
        record = data["channels"].get("xiaohongshu")
        if isinstance(record, dict):
            record["site"] = site

    if _saved_site() != site:
        state.mutate(change)


def _site_for_url(url: str) -> str:
    from agent_reach.utils.url import host_matches

    return "rednote" if host_matches(url, "rednote.com") else "xiaohongshu"


def _swap_host(url: str, site: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    return urlunsplit(parts._replace(netloc=_SITE_HOSTS[site]))


class XiaoHongShuChannel(Channel):
    name = "xiaohongshu"
    description = "小红书笔记（xiaohongshu.com / rednote.com）"

    level = "optional"
    login_url = "https://www.xiaohongshu.com/explore"
    domains = _NOTE_HOSTS
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
            (("opencli", "_opencli_search"),),
            live_test={"query": "咖啡", "limit": 2},
            public_web=("xiaohongshu.com/explore/", "xiaohongshu.com/search_result/", "xhslink.com/",
                        "rednote.com/explore/", "rednote.com/search_result/"),
        ),
        Action(
            "read",
            "Read a note (full link including xsec_token, as returned by search)",
            (Param("target", "full note link with xsec_token"),),
            (("opencli", "_opencli_read"),),
            public_web=("xiaohongshu.com/explore/", "xiaohongshu.com/search_result/", "xhslink.com/",
                        "rednote.com/explore/", "rednote.com/search_result/"),
        ),
        Action(
            "comments",
            "Read loaded comments and replies from a note; not an exhaustive export",
            (Param("target", "full note link with xsec_token"),
             Param("limit", "max top-level comments (1..50); loaded replies are included",
                   required=False, type=int, default=20)),
            (("opencli", "_opencli_comments"),),
            timeout=60,
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "xiaohongshu.com", "rednote.com", "xhslink.com")

    # ── site routing ──

    def _call(self, site: str, args, timeout: float):
        return opencli_call(site, args, timeout=timeout, login_hint=_XHS_LOGIN_HINT, channel=self.name)

    def _call_note(self, url: str, args_for, timeout: float):
        """Run a note command on the link's own site; on NEED_LOGIN retry once on the other domain."""
        from agent_reach.utils.url import host_matches

        deadline = time.monotonic() + timeout
        site = _site_for_url(url)
        try:
            return url, self._call(site, args_for(url), timeout)
        except ReachError as exc:
            left = deadline - time.monotonic()
            if exc.code != NEED_LOGIN or not host_matches(url, *_NOTE_HOSTS) or left < _MIN_ATTEMPT_S:
                raise
            other = _other(site)
            alt = _swap_host(url, other)
            return alt, self._call(other, args_for(alt), left)

    # ── unified entry backends ──

    def _opencli_search(self, *, query: str, limit: int, timeout: float) -> list:
        deadline = time.monotonic() + timeout
        first = _saved_site()
        args = ["search", query, "--limit", str(limit)]
        try:
            site, rows = first, self._call(first, args, timeout)
        except ReachError as exc:
            left = deadline - time.monotonic() - _FALLBACK_GAP_S
            if exc.code != NEED_LOGIN or left < _MIN_ATTEMPT_S:
                raise
            time.sleep(_FALLBACK_GAP_S)
            site = _other(first)
            rows = self._call(site, args, left)
        items = opencli_items(rows)[:limit]
        if not items:
            raise ReachError(UPSTREAM_BROKEN, "OpenCLI finished but returned no notes")
        _remember_site(site)
        for item in items:
            raw = dict(item.get("raw") or {})
            raw.setdefault("site", site)
            item["raw"] = raw
        return items

    def _opencli_read(self, *, target: str, timeout: float) -> list:
        from agent_reach.utils.url import host_matches

        url = str(target).strip()
        if not host_matches(url, "xiaohongshu.com", "rednote.com", "xhslink.com"):
            raise ReachError(BAD_INPUT, "target must be a full Xiaohongshu/Rednote note link including xsec_token")
        url, rows = self._call_note(url, lambda u: ["note", u], timeout)
        # OpenCLI 2.0 wraps the rows as {"ok": true, "data": [...]}; older versions return the list.
        if isinstance(rows, dict) and isinstance(rows.get("data"), list):
            rows = rows["data"]
        if isinstance(rows, list) and rows and all(isinstance(r, dict) and "field" in r and "value" in r for r in rows):
            note = {r["field"]: r["value"] for r in rows}
            note["url"] = url
            rows = [note]
        items = opencli_items(rows)
        if not items:
            raise ReachError(NOT_FOUND, "note not found")
        return items[:1]


    def validate_params(self, action, params):
        if action == "comments":
            self._validate_comments(params["target"], params["limit"])

    @staticmethod
    def _validate_comments(target, limit):
        from agent_reach.utils.url import host_matches
        try:
            import re
            from urllib.parse import urlsplit
            parsed = urlsplit(str(target).strip())
            if (not host_matches(str(target).strip(), *_NOTE_HOSTS) or parsed.scheme != "https"
                    or parsed.username or parsed.password or parsed.port not in (None, 443)
                    or not re.fullmatch(r"/(?:explore|search_result)/[A-Za-z0-9_-]+", parsed.path)):
                raise ValueError("Expected a direct note URL")
        except (ValueError, TypeError):
            raise ReachError(BAD_INPUT, "target must be a direct Xiaohongshu/Rednote note URL") from None
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ReachError(BAD_INPUT, "limit must be between 1 and 50 top-level comments")

    def _opencli_comments(self, *, target, limit, timeout):
        self._validate_comments(target, limit)
        url, rows = self._call_note(
            str(target).strip(),
            lambda u: ["comments", u, "--limit", str(limit), "--with-replies", "true"],
            timeout,
        )
        items = opencli_items(rows)
        for item in items:
            item["url"] = url
            raw = dict(item.get("raw") or {})
            raw.update(content_scope="loaded_comments", exhaustive=False)
            item["raw"] = raw
        return items

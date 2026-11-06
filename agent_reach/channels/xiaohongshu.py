# -*- coding: utf-8 -*-
"""XiaoHongShu through upstream OpenCLI in the Reach-owned browser."""

from agent_reach.backends.opencli import opencli_call, opencli_items
from agent_reach.runtime.result import BAD_INPUT, NOT_FOUND, UPSTREAM_BROKEN, ReachError

from .base import Action, Channel, Param

_XHS_LOGIN_HINT = (
    "Run agent-reach login xiaohongshu to open the Agent Reach dedicated browser. "
    "Reach first tries the existing local site login; the user completes any remaining login. Never ask for a password."
)


class XiaoHongShuChannel(Channel):
    name = "xiaohongshu"
    description = "小红书笔记"

    level = "optional"
    login_url = "https://www.xiaohongshu.com/explore"
    tools = ("opencli",)
    prereqs = ("node", "chrome")

    def setup_problems(self):
        from agent_reach.config import Config
        from agent_reach.native.xhs import _interpreter, _spider_dir
        from agent_reach.runtime.browser_binding import setup_problems

        problems = []
        if not str(Config().get("xhs_cookie") or "").strip():
            problems.append(
                "xhs_cookie is not configured; add it to ~/.agent-reach/config.yaml or set XHS_COOKIE"
            )
        interpreter = _interpreter()
        if not interpreter.is_file():
            problems.append(f"xhs_python interpreter not found: {interpreter}")
        spider = _spider_dir(interpreter)
        if not (spider / "apis").is_dir():
            problems.append(f"Spider_XHS checkout not found: {spider}")
        browser = setup_problems(self.name)
        if browser:
            problems.extend(f"opencli fallback: {problem}" for problem in browser)
        return problems

    actions = (
        Action(
            "search",
            "Search notes",
            (
                Param("query", "what to search for"),
                Param("limit", "max results", required=False, type=int, default=5),
            ),
            (("native", "_native_search"), ("opencli", "_opencli_search")),
            live_test={"query": "咖啡", "limit": 2},
            timeout=120,
            public_web=("xiaohongshu.com/explore/", "xiaohongshu.com/search_result/", "xhslink.com/"),
        ),
        Action(
            "read",
            "Read a note (full link including xsec_token, as returned by search)",
            (Param("target", "full note link with xsec_token"),),
            (("native", "_native_read"), ("opencli", "_opencli_read")),
            timeout=120,
            public_web=("xiaohongshu.com/explore/", "xiaohongshu.com/search_result/", "xhslink.com/"),
        ),
        Action(
            "comments",
            "Read loaded comments and replies from a note; not an exhaustive export",
            (Param("target", "full note link with xsec_token"),
             Param("limit", "max top-level comments (1..50); loaded replies are included",
                   required=False, type=int, default=20)),
            (("native", "_native_comments"), ("opencli", "_opencli_comments")),
            timeout=120,
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "xiaohongshu.com", "xhslink.com")

    # ── unified entry backends ──

    def _native_search(self, *, query: str, limit: int, timeout: float) -> list:
        from agent_reach.native import xhs

        return xhs.search(query=query, limit=limit, timeout=timeout)

    def _native_read(self, *, target: str, timeout: float) -> list:
        from agent_reach.native import xhs

        return xhs.read(target=target, timeout=timeout)

    def _native_comments(self, *, target: str, limit: int, timeout: float) -> list:
        from agent_reach.native import xhs

        return xhs.comments(target=target, limit=limit, timeout=timeout)

    def _opencli_search(self, *, query: str, limit: int, timeout: float) -> list:
        rows = opencli_call(
            "xiaohongshu", ["search", query, "--limit", str(limit)],
            timeout=timeout, login_hint=_XHS_LOGIN_HINT,
        )
        items = opencli_items(rows)[:limit]
        if not items:
            raise ReachError(
                UPSTREAM_BROKEN,
                "OpenCLI finished but returned no notes",
            )
        return items

    def _opencli_read(self, *, target: str, timeout: float) -> list:
        from agent_reach.utils.url import host_matches

        url = str(target).strip()
        if not host_matches(url, "xiaohongshu.com", "xhslink.com"):
            raise ReachError(BAD_INPUT, "target must be a full Xiaohongshu note link including xsec_token")
        rows = opencli_call("xiaohongshu", ["note", url], timeout=timeout, login_hint=_XHS_LOGIN_HINT)
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
            if (not host_matches(str(target).strip(), "xiaohongshu.com") or parsed.scheme != "https"
                    or parsed.username or parsed.password or parsed.port not in (None, 443)
                    or not re.fullmatch(r"/(?:explore|search_result)/[A-Za-z0-9_-]+", parsed.path)):
                raise ValueError("Expected a direct note URL")
        except (ValueError, TypeError):
            raise ReachError(BAD_INPUT, "target must be a direct Xiaohongshu note URL") from None
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ReachError(BAD_INPUT, "limit must be between 1 and 50 top-level comments")

    def _opencli_comments(self, *, target, limit, timeout):
        self._validate_comments(target, limit)
        rows = opencli_call(
            self.name, ["comments", str(target).strip(), "--limit", str(limit),
                        "--with-replies", "true"],
            timeout=timeout, login_hint=_XHS_LOGIN_HINT,
        )
        items = opencli_items(rows)
        for item in items:
            item["url"] = str(target).strip()
            raw = dict(item.get("raw") or {})
            raw.update(content_scope="loaded_comments", exhaustive=False)
            item["raw"] = raw
        return items

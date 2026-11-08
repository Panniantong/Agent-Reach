# -*- coding: utf-8 -*-
"""Read-only Zhihu actions through OpenCLI in the Reach-owned browser."""

import re
from urllib.parse import urlsplit

from agent_reach.backends.opencli import opencli_call, opencli_items
from agent_reach.runtime.result import (
    BAD_INPUT,
    NOT_FOUND,
    UPSTREAM_BROKEN,
    ReachError,
    unix_to_iso,
)

from .base import Action, Channel, Param

_ZHIHU_LOGIN_HINT = (
    "Run agent-reach login zhihu to open the Agent Reach dedicated browser. "
    "The user completes login in that browser. Never request account credentials."
)
_ANSWER_EXAMPLE = "https://www.zhihu.com/answer/1937205528846655537"


def _target(target: str) -> tuple[str, str]:
    """Return the resource kind and lossless ID, without navigating anywhere."""
    if not isinstance(target, str) or not target or any(
        char.isspace() or ord(char) < 32 or ord(char) == 127 for char in target
    ):
        raise ReachError(BAD_INPUT, "target must be a Zhihu question/answer URL or an answer ID")
    if re.fullmatch(r"[0-9]+", target):
        return "answer", target
    try:
        parsed = urlsplit(target)
        if parsed.scheme != "https" or parsed.netloc.lower() not in {
            "zhihu.com", "www.zhihu.com", "zhihu.com:443", "www.zhihu.com:443",
        }:
            raise ValueError("Expected a direct HTTPS Zhihu URL")
        match = re.fullmatch(r"/question/([0-9]+)(?:/answer/([0-9]+))?", parsed.path)
        if match:
            return ("answer", match[2]) if match[2] else ("question", match[1])
        match = re.fullmatch(r"/answer/([0-9]+)", parsed.path)
        if match:
            return "answer", match[1]
    except ValueError:
        pass
    raise ReachError(BAD_INPUT, "target must be a direct HTTPS Zhihu question/answer URL or an answer ID")


def _limit(name: str, value: int, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ReachError(BAD_INPUT, f"{name} must be an integer between {minimum} and {maximum}")


def _require_content(items: list) -> None:
    if any(not isinstance(item.get("text"), str) or not item["text"].strip() for item in items):
        raise ReachError(UPSTREAM_BROKEN, "OpenCLI returned Zhihu rows without readable content")


class ZhihuChannel(Channel):
    name = "zhihu"
    description = "知乎问题、回答与评论"
    level = "optional"
    tools = ("opencli",)
    prereqs = ("node", "chrome")
    login_url = "https://www.zhihu.com/signin"
    domains = ("zhihu.com",)

    actions = (
        Action(
            "search", "Search Zhihu titles, authors and links (including articles)",
            (
                Param("query", "what to search for"),
                Param("limit", "max results (1..50)", required=False, type=int, default=5),
            ),
            (("opencli", "_opencli_search"),),
            live_test={"query": "大模型", "limit": 2},
        ),
        Action(
            "hot", "Read the Zhihu hot list",
            (Param("limit", "max results (1..50)", required=False, type=int, default=5),),
            (("opencli", "_opencli_hot"),),
            live_test={"limit": 2},
        ),
        Action(
            "read", "Read a full answer or a question's answer excerpts (up to 200 characters each)",
            (
                Param("target", "HTTPS question/answer URL or answer ID"),
                Param("limit", "max answer excerpts for a question (1..50)", required=False, type=int, default=5),
            ),
            (("opencli", "_opencli_read"),),
            live_test={"target": _ANSWER_EXAMPLE, "limit": 2},
        ),
        Action(
            "comments", "Read loaded answer comments and replies; not an exhaustive comment tree",
            (
                Param("target", "HTTPS answer URL or answer ID"),
                Param("limit", "max top-level comments (1..50); replies are included", required=False, type=int, default=20),
                Param("replies-limit", "max loaded replies per comment (0..20)", required=False, type=int, default=3),
            ),
            (("opencli", "_opencli_comments"),),
            live_test={"target": _ANSWER_EXAMPLE, "limit": 2, "replies-limit": 1},
            timeout=60,
        ),
    )

    def setup_problems(self):
        from agent_reach.runtime.browser_binding import setup_problems

        return setup_problems(self.name)

    def can_handle(self, url: str) -> bool:
        if not isinstance(url, str) or re.fullmatch(r"[0-9]+", url):
            return False
        try:
            _target(url)
        except ReachError:
            return False
        return True

    def validate_params(self, action, params):
        _limit("limit", params["limit"], 1, 50)
        if action in {"read", "comments"}:
            kind, _ = _target(params["target"])
            if action == "comments":
                if kind != "answer":
                    raise ReachError(BAD_INPUT, "comments requires an answer URL or answer ID")
                _limit("replies-limit", params["replies-limit"], 0, 20)

    def _opencli_search(self, *, query: str, limit: int, timeout: float) -> list:
        self.validate_params("search", {"query": query, "limit": limit})
        rows = opencli_call(
            self.name, ["search", query, "--limit", str(limit)],
            timeout=timeout, login_hint=_ZHIHU_LOGIN_HINT,
        )
        items = opencli_items(rows)[:limit]
        if not items:
            raise ReachError(UPSTREAM_BROKEN, "OpenCLI returned no Zhihu search results")
        for item in items:
            # Search only supplies discovery metadata, including unsupported article links.
            item["text"] = None
            item["raw"] = dict(item["raw"], content_scope="search_result", exhaustive=False)
        return items

    def _opencli_hot(self, *, limit: int, timeout: float) -> list:
        self.validate_params("hot", {"limit": limit})
        rows = opencli_call(
            self.name, ["hot", "--limit", str(limit)],
            timeout=timeout, login_hint=_ZHIHU_LOGIN_HINT,
        )
        items = opencli_items(rows)[:limit]
        if not items:
            raise ReachError(UPSTREAM_BROKEN, "OpenCLI returned an empty Zhihu hot list")
        return items

    def _opencli_read(self, *, target: str, limit: int, timeout: float) -> list:
        self.validate_params("read", {"target": target, "limit": limit})
        kind, resource_id = _target(target)
        args = (["question", resource_id, "--limit", str(limit)] if kind == "question"
                else ["answer-detail", resource_id, "--max-content", "0"])
        rows = opencli_call(self.name, args, timeout=timeout, login_hint=_ZHIHU_LOGIN_HINT)
        items = opencli_items(rows)[:limit if kind == "question" else 1]
        if not items:
            raise ReachError(NOT_FOUND, "Zhihu question/answer was not found")
        _require_content(items)
        for item in items:
            raw = item["raw"]
            if kind == "question":
                item["raw"] = dict(raw, content_scope="answer_excerpt", exhaustive=False)
            else:
                item["title"] = raw.get("question_title") or None
                item["url"] = item["url"] or f"https://www.zhihu.com/answer/{resource_id}"
                created_at = raw.get("created_at")
                if isinstance(created_at, (int, float)) and not isinstance(created_at, bool):
                    item["published_at"] = unix_to_iso(created_at)
        return items

    def _opencli_comments(self, *, target: str, limit: int, timeout: float, **params) -> list:
        self.validate_params("comments", {"target": target, "limit": limit, **params})
        _, answer_id = _target(target)
        rows = opencli_call(
            self.name, ["answer-comments", answer_id, "--limit", str(limit),
                        "--replies-limit", str(params["replies-limit"])],
            timeout=timeout, login_hint=_ZHIHU_LOGIN_HINT,
        )
        # The upstream limit applies to roots; slicing the result would discard replies.
        items = opencli_items(rows)
        _require_content(items)
        for item in items:
            item["raw"] = dict(item["raw"], content_scope="loaded_comments", exhaustive=False)
        return items

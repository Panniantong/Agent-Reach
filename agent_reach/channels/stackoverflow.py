# -*- coding: utf-8 -*-
"""Stack Overflow — public API channel for Q&A search, questions, and users.

Uses the official Stack Exchange API v2.3 (https://api.stackexchange.com/2.3/).
No key required — anonymous access is rate-limited (~300 requests/day per IP;
a free registered key raises this to 10k/day). Every method takes a `site`
argument (default "stackoverflow") so other Stack Exchange sites work too
(e.g. "serverfault", "superuser", "askubuntu", "math").

Note: the Stack Exchange API ALWAYS gzip-compresses responses, so the fetch
helper must decompress regardless of the request's Accept-Encoding.
"""

import gzip
import html
import json
import urllib.parse
import urllib.request
from typing import Any

from .base import Channel

_UA = "agent-reach/1.0"
_TIMEOUT = 10
_BASE = "https://api.stackexchange.com/2.3"
# Default filter that includes question/answer body (HTML); the API omits body
# unless an explicit filter asks for it. "withbody" is a built-in named filter.
_WITHBODY = "withbody"


def _get_json(url: str) -> Any:
    """Fetch *url* and return parsed JSON, decompressing gzip if present.

    The Stack Exchange API always gzips its responses, so we decode based on
    the Content-Encoding header (and fall back to a gzip-magic-byte sniff).
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept-Encoding": "gzip"}
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        raw = resp.read()
        encoding = (resp.headers.get("Content-Encoding") or "").lower()
    if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def _owner_name(item: dict) -> str:
    return (item.get("owner") or {}).get("display_name", "")


class StackOverflowChannel(Channel):
    name = "stackoverflow"
    description = "Stack Overflow 问题搜索、问答详情、标签与用户（Stack Exchange API）"
    backends = ["Stack Exchange API (public)"]
    tier = 0

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "stackoverflow.com" in d

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        try:
            _get_json(f"{_BASE}/info?site=stackoverflow")
            self.active_backend = self.backends[0]
            return "ok", "公开 API 可用（问题搜索、问答详情、标签、用户；匿名约 300 次/天）"
        except Exception as e:
            self.active_backend = None
            return "warn", f"Stack Exchange API 连接失败（可能需要代理）：{e}"

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    def _format_question(self, item: dict) -> dict:
        """Normalize a question item into a flat dict (no body)."""
        return {
            "question_id": item.get("question_id", 0),
            # Titles arrive HTML-escaped (e.g. Rust&#39;s) — unescape for agents.
            "title": html.unescape(item.get("title", "")),
            "link": item.get("link", ""),
            "score": item.get("score", 0),
            "answer_count": item.get("answer_count", 0),
            "is_answered": item.get("is_answered", False),
            "accepted_answer_id": item.get("accepted_answer_id"),
            "view_count": item.get("view_count", 0),
            "tags": item.get("tags", []) or [],
            "owner": _owner_name(item),
            "created": item.get("creation_date", 0),
        }

    def search(
        self,
        query: str,
        limit: int = 10,
        tag: str | None = None,
        site: str = "stackoverflow",
    ) -> list:
        """搜索问题（按相关性排序）。

        Args:
            query: 搜索关键词（全文，匹配标题和正文）
            limit: 最多返回条数
            tag:   可选，限定标签，如 "python"、"rust"
            site:  Stack Exchange 站点，默认 "stackoverflow"

        Returns a list of dicts with keys:
          question_id, title, link, score, answer_count, is_answered,
          accepted_answer_id, view_count, tags, owner, created
        """
        params = {
            "order": "desc",
            "sort": "relevance",
            "q": query,
            "pagesize": limit,
            "site": site,
        }
        if tag:
            params["tagged"] = tag
        data = _get_json(f"{_BASE}/search/advanced?{urllib.parse.urlencode(params)}")
        return [self._format_question(it) for it in (data.get("items") or [])[:limit]]

    def get_question(
        self, question_id: int, answer_limit: int = 5, site: str = "stackoverflow"
    ) -> dict:
        """获取问题详情和高赞回答（含正文 HTML）。

        Args:
            question_id:  问题 ID（从 URL .../questions/<id>/... 获取）
            answer_limit: 最多返回的回答条数（按票数排序）
            site:         Stack Exchange 站点

        Returns a dict with keys:
          question_id, title, link, score, answer_count, is_answered,
          accepted_answer_id, view_count, tags, owner, created, body,
          answers (list of dicts with: answer_id, score, is_accepted, body,
          owner, created)
        """
        q_params = {"site": site, "filter": _WITHBODY}
        q_data = _get_json(
            f"{_BASE}/questions/{question_id}?{urllib.parse.urlencode(q_params)}"
        )
        items = q_data.get("items") or []
        if not items:
            return {"question_id": question_id, "error": "question not found"}
        question = self._format_question(items[0])
        question["body"] = items[0].get("body", "")

        a_params = {
            "order": "desc",
            "sort": "votes",
            "pagesize": answer_limit,
            "site": site,
            "filter": _WITHBODY,
        }
        a_data = _get_json(
            f"{_BASE}/questions/{question_id}/answers?{urllib.parse.urlencode(a_params)}"
        )
        question["answers"] = [
            {
                "answer_id": a.get("answer_id", 0),
                "score": a.get("score", 0),
                "is_accepted": a.get("is_accepted", False),
                "body": a.get("body", ""),
                "owner": _owner_name(a),
                "created": a.get("creation_date", 0),
            }
            for a in (a_data.get("items") or [])[:answer_limit]
        ]
        return question

    def get_tag_questions(
        self, tag: str, limit: int = 20, site: str = "stackoverflow"
    ) -> list:
        """获取某标签下的高票问题。

        Args:
            tag:   标签名，如 "python"、"rust"、"asyncio"
            limit: 最多返回条数
            site:  Stack Exchange 站点

        Returns a list of dicts (same shape as search()).
        """
        params = {
            "order": "desc",
            "sort": "votes",
            "tagged": tag,
            "pagesize": limit,
            "site": site,
        }
        data = _get_json(f"{_BASE}/questions?{urllib.parse.urlencode(params)}")
        return [self._format_question(it) for it in (data.get("items") or [])[:limit]]

    def get_user(self, user_id: int, site: str = "stackoverflow") -> dict:
        """获取用户信息。

        Args:
            user_id: 用户数字 ID（从 URL .../users/<id>/... 获取）
            site:    Stack Exchange 站点

        Returns a dict with keys:
          user_id, display_name, link, reputation, created, location,
          badge_gold, badge_silver, badge_bronze
        """
        params = {"site": site}
        data = _get_json(f"{_BASE}/users/{user_id}?{urllib.parse.urlencode(params)}")
        items = data.get("items") or []
        if not items:
            return {"user_id": user_id, "error": "user not found"}
        u = items[0]
        badges = u.get("badge_counts") or {}
        return {
            "user_id": u.get("user_id", user_id),
            "display_name": u.get("display_name", ""),
            "link": u.get("link", ""),
            "reputation": u.get("reputation", 0),
            "created": u.get("creation_date", 0),
            "location": u.get("location", ""),
            "badge_gold": badges.get("gold", 0),
            "badge_silver": badges.get("silver", 0),
            "badge_bronze": badges.get("bronze", 0),
        }

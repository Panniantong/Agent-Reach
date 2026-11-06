# -*- coding: utf-8 -*-
"""Normalize XiaoHongShu payloads and map upstream failures for the native backend.

Upstream ``code`` values are not portable across actions: ``300031`` means
risk control during search, but "note deleted or private" when reading a note
or its comments. ``map_xhs_error`` therefore always takes the action name.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from agent_reach.runtime.result import (
    NEED_LOGIN,
    NOT_FOUND,
    PLATFORM_BLOCKED,
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
    unix_to_iso,
)
from agent_reach.utils.text import scrub_url_credentials

#: Upstream codes that the local xhs_api.py already treats as risk control.
XHS_RISK_CODES = frozenset({"300031", "300035", "2001", "1001", "2002", "4001", "-1"})
XHS_RISK_MESSAGES = (
    "风控",
    "频繁",
    "验证码",
    "限制",
    "暂时无法浏览",
    "操作过于频繁",
    "稍后再试",
    "too many",
    "captcha",
)
_NOT_FOUND_MESSAGES = ("已删除", "不存在", "设私", "私密", "not found", "not exist", "deleted", "private")
_NEED_LOGIN_MESSAGES = ("登录", "login", "log in", "sign in", "unauthorized", "401")
_MAX_MESSAGE = 500
_XHS_QUERY_SECRET_RE = re.compile(r"(?i)\b(xsec_(?:token|source))\s*=\s*[^\s&#\"']+")


def _clean_message(message: object) -> str:
    """Upstream text may echo the note URL, including its xsec_token."""
    text = _XHS_QUERY_SECRET_RE.sub(r"\1=***", str(message))
    return scrub_url_credentials(text).strip()[:_MAX_MESSAGE]


def _payload_fields(payload: dict) -> tuple[str, str]:
    raw_data = payload.get("data")
    data: dict = raw_data if isinstance(raw_data, dict) else {}
    code = payload.get("code")
    if code in (None, "") and data:
        code = data.get("code")
    message = payload.get("msg") or payload.get("message") or data.get("msg") or ""
    return str(code or "").strip(), _clean_message(message)


def _contains(message: str, words: tuple[str, ...]) -> bool:
    lowered = message.casefold()
    return any(word.casefold() in lowered for word in words)


def map_xhs_error(action: str, payload: Any) -> Optional[ReachError]:
    """Return the ReachError for an upstream payload, or None when it succeeded."""
    if not isinstance(payload, dict):
        return ReachError(UPSTREAM_BROKEN, "XiaoHongShu returned an unexpected payload")

    code, message = _payload_fields(payload)

    # detail/comments 300031 is "deleted or private", never risk control
    # (see 改造计划 §6); only search treats the same code as a block.
    if action in {"read", "comments"} and code == "300031":
        return ReachError(NOT_FOUND, message or "note not found or private")

    # A successful payload is trusted even if its message happens to contain a
    # risk/login word (for example "登录成功").
    if payload.get("success") is True:
        return None

    if _contains(message, XHS_RISK_MESSAGES) or code in XHS_RISK_CODES:
        return ReachError(
            PLATFORM_BLOCKED,
            message or f"XiaoHongShu risk control (code {code or 'unknown'})",
        )

    if action in {"read", "comments"} and _contains(message, _NOT_FOUND_MESSAGES):
        return ReachError(NOT_FOUND, message or "note not found")

    if _contains(message, _NEED_LOGIN_MESSAGES):
        return ReachError(NEED_LOGIN, message or "XiaoHongShu rejected the saved login")

    # Missing/false success with no mapped cause is a broken upstream response,
    # not a silent empty success.
    return ReachError(
        UPSTREAM_BROKEN,
        message or f"XiaoHongShu request failed (code {code or 'unknown'})",
    )


def _published_at(value: Any) -> Optional[str]:
    """XHS detail uses millisecond timestamps; ``unix_to_iso`` expects seconds."""
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds > 10_000_000_000:  # 13-digit milliseconds, not 10-digit seconds
        seconds //= 1000
    return unix_to_iso(seconds)


def note_item(row: Any, *, url: Optional[str] = None) -> dict:
    """One search result or note detail as a unified item."""
    row = dict(row or {}) if isinstance(row, dict) else {}
    return make_item(
        title=row.get("title") or row.get("display_title"),
        url=url or row.get("url"),
        author=row.get("nickname") or row.get("author"),
        published_at=_published_at(row.get("publish_time")),
        text=row.get("desc"),
        raw=row,
    )


def comment_item(row: Any, *, url: Optional[str] = None) -> dict:
    """One top-level comment; loaded replies stay under ``raw['sub']``."""
    row = dict(row or {}) if isinstance(row, dict) else {}
    raw = dict(row)
    raw.update(content_scope="loaded_comments", exhaustive=False)
    return make_item(
        url=url,
        author=row.get("nickname"),
        text=row.get("content"),
        raw=raw,
    )

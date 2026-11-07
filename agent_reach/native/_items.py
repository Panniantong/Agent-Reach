# -*- coding: utf-8 -*-
"""Item builders and action-aware error mapping shared by native backends.

`make_item` / `unix_to_iso` already live in `agent_reach.runtime.result`; this
module only adapts each platform's payload into that shape.
"""

from __future__ import annotations

import html
import re
from typing import Any, Dict, Optional

from agent_reach.runtime.result import (
    BAD_INPUT,
    NEED_LOGIN,
    NEED_SETUP,
    NOT_FOUND,
    PLATFORM_BLOCKED,
    RATE_LIMITED,
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
    unix_to_iso,
)

_TAG_RE = re.compile(r"<[^>]+>")

_BILI_LOGIN_HINT = (
    "Bilibili needs a login for this request. Set `bili_cookie` in "
    "~/.agent-reach/config.yaml (or export BILI_COOKIE), or sign in to "
    "bilibili.com in Chrome; agent-reach can also fall back to bili-cli's own login."
)

BILI_NO_KEY_HINT = (
    "Set `summary_api_key` in ~/.agent-reach/config.yaml (or export "
    "SUMMARY_API_KEY); optional: `summary_base_url` and `summary_model`."
)


def _strip_html(value: Any) -> Optional[str]:
    """Search titles include <em> highlight tags; plain text is what agents need."""
    if value is None:
        return None
    text = html.unescape(_TAG_RE.sub("", str(value))).strip()
    return text or None


def video_item(info: Dict[str, Any]) -> dict:
    """One item for `read`, built from the native `get_video_info` payload."""
    bvid = info.get("bvid")
    raw = {
        key: info.get(key)
        for key in (
            "bvid",
            "aid",
            "cid",
            "duration",
            "pubdate",
            "views",
            "stat",
            "page_count",
            "pages",
            "subtitle_allow_submit",
        )
        if info.get(key) is not None
    }
    return make_item(
        title=info.get("title"),
        url=info.get("url") or (f"https://www.bilibili.com/video/{bvid}" if bvid else None),
        author=info.get("owner"),
        published_at=unix_to_iso(info.get("pubdate")),
        text=info.get("desc"),
        raw=raw,
    )


def search_item(row: Dict[str, Any]) -> dict:
    """One item for `search`, built from a WBI search result row."""
    bvid = str(row.get("bvid") or "")
    # Prefer the canonical BV link: `arcurl` often uses the av-number form,
    # which the channel's read target parser does not accept.
    url = (
        f"https://www.bilibili.com/video/{bvid}"
        if bvid
        else row.get("arcurl") or None
    )
    raw = {
        key: row.get(key)
        for key in ("bvid", "aid", "author", "pubdate", "play", "pic", "duration", "type")
        if row.get(key) is not None
    }
    return make_item(
        title=_strip_html(row.get("title")),
        url=url,
        author=_strip_html(row.get("author")),
        published_at=unix_to_iso(row.get("pubdate")),
        text=_strip_html(row.get("description")),
        raw=raw,
    )


def subtitle_item(result: Dict[str, Any], language: Optional[str] = None) -> dict:
    """One item for `subtitle`; `result` is the native `extract_subtitle` dict."""
    part = (result.get("parts") or [{}])[0]
    tracks = part.get("subtitles") or {}
    if language:
        texts = [
            track.get("text")
            for code, track in tracks.items()
            if code == language and track.get("text")
        ]
    else:
        texts = [track.get("text") for track in tracks.values() if track.get("text")]
    bvid = result.get("bvid")
    return make_item(
        title=result.get("title"),
        url=result.get("url") or (f"https://www.bilibili.com/video/{bvid}" if bvid else None),
        author=result.get("owner"),
        published_at=unix_to_iso(result.get("pubdate")),
        text="\n\n".join(texts) or None,
        raw={
            "bvid": bvid,
            "part": part.get("part"),
            "part_name": part.get("part_name"),
            "page_count": result.get("page_count"),
            "languages": sorted(tracks),
            "line_count": sum(int(track.get("line_count") or 0) for track in tracks.values()),
        },
    )


def summary_item(
    result: Dict[str, Any],
    text: str,
    model: str,
    *,
    input_characters: Optional[int] = None,
    truncated: Optional[bool] = None,
) -> dict:
    """One item for `summary`; `text` is the model's final answer."""
    part = (result.get("parts") or [{}])[0]
    bvid = result.get("bvid")
    return make_item(
        title=result.get("title"),
        url=result.get("url") or (f"https://www.bilibili.com/video/{bvid}" if bvid else None),
        author=result.get("owner"),
        published_at=unix_to_iso(result.get("pubdate")),
        text=text,
        raw={
            "bvid": bvid,
            "part": part.get("part"),
            "part_name": part.get("part_name"),
            "model": model,
            "characters": len(text),
            "input_characters": input_characters,
            "truncated": truncated,
        },
    )


def map_bili_error(code: Any, message: Any, action: str = "read") -> ReachError:
    """Map a Bilibili API code / HTTP status to a unified error.

    `action` labels the failing operation in fallback messages. Credential
    distinctions (anonymous 401/403 vs a rejected login) live in the caller,
    which is the only place that knows whether a session was supplied.
    Returning (not raising) keeps the mapping trivially testable; callers
    raise the result.
    """
    detail = (_strip_html(message) or "")[:500]
    try:
        numeric = int(code)
    except (TypeError, ValueError):
        numeric = None

    if numeric in (-404, 404):
        return ReachError(NOT_FOUND, detail or "video not found")
    if numeric in (429, -509, -799):
        return ReachError(RATE_LIMITED, detail or "Bilibili rate limited the request")
    if numeric in (-412, -352, 412):
        # WBI risk-control rejection: let bili-cli take over instead of
        # treating this as an account-level block.
        return ReachError(
            UPSTREAM_BROKEN,
            detail or f"Bilibili rejected the request (code {code})",
        )
    if numeric == -101:
        # No usable local login: non-final so the bili-cli leg can run.
        return ReachError(
            NEED_SETUP,
            detail or "Bilibili needs a login for this request",
            hint=_BILI_LOGIN_HINT,
        )
    if numeric in (401, 403):
        # A credential was supplied and the platform refused it.
        return ReachError(
            NEED_LOGIN,
            detail or "Bilibili rejected the provided login",
            hint=_BILI_LOGIN_HINT,
        )
    if numeric in (-102, -403, -10403):
        return ReachError(PLATFORM_BLOCKED, detail or "Bilibili blocked this account")
    if numeric == -400:
        return ReachError(BAD_INPUT, detail or "Bilibili rejected the request as invalid")
    return ReachError(
        UPSTREAM_BROKEN, detail or f"Bilibili {action} failed (code {code})"
    )

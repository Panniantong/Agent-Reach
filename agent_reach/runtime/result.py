"""Unified result envelope and error codes for the agent-facing entry point.

Every unified command prints exactly one JSON object with this shape:

    {schema_version, ok, channel, action, backend, items, meta, error}

`schema_version` only changes on incompatible shape changes. Agents branch
on `ok` and `error.code`; they should never need to parse upstream output.
"""

from __future__ import annotations

import datetime as _dt
import socket
import subprocess
import urllib.error
from typing import Any, Optional

from agent_reach.utils.text import scrub_url_credentials

SCHEMA_VERSION = 1

NEED_SETUP = "NEED_SETUP"
NEED_LOGIN = "NEED_LOGIN"
UPSTREAM_BROKEN = "UPSTREAM_BROKEN"
TIMEOUT = "TIMEOUT"
RATE_LIMITED = "RATE_LIMITED"
NOT_FOUND = "NOT_FOUND"
BAD_INPUT = "BAD_INPUT"

#: Codes where trying another backend cannot help.
FINAL_CODES = frozenset({NOT_FOUND, BAD_INPUT})

DEFAULT_HINTS = {
    NEED_SETUP: "This backend is not installed. Ask the user to run `agent-reach doctor` for setup steps.",
    NEED_LOGIN: "Login is required or expired. Guide the user to log in themselves; never log in on their behalf.",
    UPSTREAM_BROKEN: "The upstream tool failed. Tell the user this channel is unavailable right now; do not retry in a loop.",
    TIMEOUT: "No backend answered in time. Retry later, or pass a larger --timeout.",
    RATE_LIMITED: "Rate limited by the platform. Wait a while before retrying.",
    NOT_FOUND: "The requested content does not exist. Check the link or id.",
    BAD_INPUT: "Invalid arguments. Run `agent-reach channels` to see valid usage.",
}

_MAX_MESSAGE_CHARS = 500


class ReachError(Exception):
    """An upstream failure already mapped to a unified error code."""

    def __init__(self, code: str, message: str, hint: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


def _clean(text: object) -> str:
    return scrub_url_credentials(str(text)).strip()[:_MAX_MESSAGE_CHARS]


def classify(exc: BaseException) -> ReachError:
    """Map any exception raised by a backend to a ReachError."""
    if isinstance(exc, ReachError):
        return exc
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 404:
            return ReachError(NOT_FOUND, f"HTTP 404: {_clean(exc.reason)}")
        if exc.code == 429:
            return ReachError(RATE_LIMITED, "HTTP 429")
        return ReachError(UPSTREAM_BROKEN, f"HTTP {exc.code}: {_clean(exc.reason)}")
    if isinstance(exc, (subprocess.TimeoutExpired, socket.timeout, TimeoutError)):
        return ReachError(TIMEOUT, "upstream did not answer in time")
    if isinstance(exc, urllib.error.URLError):
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            return ReachError(TIMEOUT, "upstream did not answer in time")
        return ReachError(UPSTREAM_BROKEN, f"network error: {_clean(exc.reason)}")
    if isinstance(exc, FileNotFoundError):
        return ReachError(NEED_SETUP, f"missing executable: {_clean(exc.filename or exc)}")
    return ReachError(UPSTREAM_BROKEN, f"{type(exc).__name__}: {_clean(exc)}")


def make_item(
    *,
    title: Optional[str] = None,
    url: Optional[str] = None,
    author: Optional[str] = None,
    published_at: Optional[str] = None,
    text: Optional[str] = None,
    raw: Any = None,
) -> dict:
    """One normalized item. Missing fields are null; `raw` keeps upstream data."""
    return {
        "title": title or None,
        "url": url or None,
        "author": author or None,
        "published_at": published_at or None,
        "text": text or None,
        "raw": raw,
    }


def unix_to_iso(value: Any) -> Optional[str]:
    """Convert a unix timestamp to ISO 8601 UTC, or None."""
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return _dt.datetime.fromtimestamp(seconds, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def envelope(
    *,
    channel: Optional[str],
    action: Optional[str],
    backend: Optional[str] = None,
    items: Optional[list] = None,
    elapsed_ms: int = 0,
    attempts: Optional[list] = None,
    error: Optional[ReachError] = None,
) -> dict:
    """Build the unified output object."""
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": error is None,
        "channel": channel,
        "action": action,
        "backend": backend if error is None else None,
        "items": list(items or []) if error is None else [],
        "meta": {"elapsed_ms": elapsed_ms, "attempts": list(attempts or [])},
        "error": None
        if error is None
        else {
            "code": error.code,
            "message": error.message,
            "hint": error.hint or DEFAULT_HINTS.get(error.code, ""),
        },
    }

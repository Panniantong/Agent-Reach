# -*- coding: utf-8 -*-
"""V2EX — public API channel for topics, nodes, users, and replies."""

import http.client
import json
import re
import shutil
import ssl
import subprocess
import urllib.request
from typing import Any
from urllib.parse import urlencode, urlsplit

from agent_reach.runtime.result import BAD_INPUT, NOT_FOUND, ReachError, make_item, unix_to_iso
from agent_reach.utils.process import utf8_subprocess_env

from .base import Action, Channel, Param

_UA = "agent-reach/1.0"
_TIMEOUT = 10
_MAX_RESPONSE_BYTES = 1024 * 1024
_API_BASE = "https://www.v2ex.com"


def _v2ex_url(path: str, **params: Any) -> str:
    """Build a V2EX URL without letting caller values alter its query."""
    return f"{_API_BASE}{path}?{urlencode(params)}"


def _validate_api_url(url: str) -> None:
    """Allow only the public V2EX HTTPS JSON API."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid V2EX API URL") from exc
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() not in {"v2ex.com", "www.v2ex.com"}
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith("/api/")
    ):
        raise ValueError("only the V2EX HTTPS API is allowed")


def _get_json_with_urllib(url: str) -> Any:
    """Fetch JSON with Python's standard HTTP stack."""
    _validate_api_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        raw = resp.read(_MAX_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError("V2EX API response exceeds the 1 MiB safety limit")
    return json.loads(raw.decode("utf-8"))


def _is_unexpected_tls_eof(error: BaseException) -> bool:
    """Return whether an exception chain contains the retryable TLS EOF."""
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, ssl.SSLError) and not isinstance(
            current, ssl.SSLCertVerificationError
        ):
            text = str(current).casefold()
            if (
                "unexpected_eof_while_reading" in text
                or "eof occurred in violation of protocol" in text
            ):
                return True
        for nested in (
            getattr(current, "reason", None),
            current.__cause__,
            current.__context__,
        ):
            if isinstance(nested, BaseException):
                pending.append(nested)
    return False


def _get_json_with_curl(url: str) -> Any:
    """Fetch bounded JSON with the OS curl TLS stack."""
    _validate_api_url(url)
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("curl is unavailable for the V2EX TLS fallback")

    command = [
        curl,
        "--fail",
        "--silent",
        "--show-error",
        "--proto",
        "=https",
        "--connect-timeout",
        "5",
        "--max-time",
        str(_TIMEOUT),
        "--max-filesize",
        str(_MAX_RESPONSE_BYTES),
        "--header",
        f"User-Agent: {_UA}",
        "--url",
        url,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT + 2,
            env=utf8_subprocess_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("curl could not complete the V2EX TLS fallback") from exc
    if result.returncode != 0:
        raise RuntimeError("curl could not complete the V2EX TLS fallback")
    if len(result.stdout.encode("utf-8")) > _MAX_RESPONSE_BYTES:
        raise ValueError("V2EX API response exceeds the 1 MiB safety limit")
    return json.loads(result.stdout)


def _get_json(url: str) -> Any:
    """Fetch JSON, retrying TLS EOF or a truncated HTTP response once via native curl."""
    try:
        return _get_json_with_urllib(url)
    except Exception as exc:
        if isinstance(exc, ssl.SSLCertVerificationError):
            raise
        if not isinstance(exc, http.client.IncompleteRead) and not _is_unexpected_tls_eof(exc):
            raise
        return _get_json_with_curl(url)


_TOPIC_URL_RE = re.compile(r"^(?:https?://)?(?:www\.)?v2ex\.com/t/(\d+)")


def _parse_topic_id(target: str) -> int:
    """Accept a topic id or a https://www.v2ex.com/t/<id> link."""
    t = str(target).strip()
    if t.isdigit():
        return int(t)
    match = _TOPIC_URL_RE.match(t)
    if match:
        return int(match.group(1))
    raise ReachError(BAD_INPUT, "target must be a V2EX topic link (https://www.v2ex.com/t/<id>) or id")


def _topic_item(topic: dict, text: Any = None, raw: Any = None) -> dict:
    member = topic.get("member") or {}
    return make_item(
        title=topic.get("title"),
        url=topic.get("url"),
        author=member.get("username"),
        published_at=unix_to_iso(topic.get("created")),
        text=topic.get("content") if text is None else text,
        raw=topic if raw is None else raw,
    )


class V2EXChannel(Channel):
    name = "v2ex"
    description = "V2EX 节点、主题与回复"

    level = "default"
    actions = (
        Action(
            "hot",
            "Today's hot topics",
            (Param("limit", "max items", required=False, type=int, default=10),),
            (("v2ex-api", "_api_hot"),),
            live_test={"limit": 3},
        ),
        Action(
            "node",
            "Latest topics in a node",
            (
                Param("node_name", "node name, e.g. python, programmer, jobs"),
                Param("limit", "max items", required=False, type=int, default=10),
            ),
            (("v2ex-api", "_api_node"),),
            live_test={"node_name": "python", "limit": 3},
        ),
        Action(
            "read",
            "Read a topic and its replies",
            (Param("target", "topic link or id"),),
            (("v2ex-api", "_api_read"),),
            live_test={"target": "https://www.v2ex.com/t/1000"},
        ),
        Action(
            "user",
            "A member's profile",
            (Param("username", "V2EX username"),),
            (("v2ex-api", "_api_user"),),
            live_test={"username": "Livid"},
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "v2ex.com")

    # ------------------------------------------------------------------ #
    # Unified entry backends
    # ------------------------------------------------------------------ #

    def _api_hot(self, *, limit: int, timeout: float) -> list:
        data = _get_json("https://www.v2ex.com/api/topics/hot.json")
        return [_topic_item(t) for t in data[:limit]]

    def _api_node(self, *, node_name: str, limit: int, timeout: float) -> list:
        data = _get_json(_v2ex_url("/api/topics/show.json", node_name=node_name, page=1))
        if not isinstance(data, list):
            raise ReachError(NOT_FOUND, f"V2EX node not found: {node_name}")
        return [_topic_item(t) for t in data[:limit]]

    def _api_read(self, *, target: str, timeout: float) -> list:
        topic_id = _parse_topic_id(target)
        data = _get_json(_v2ex_url("/api/topics/show.json", id=topic_id))
        topic = data[0] if isinstance(data, list) and data else data
        if not isinstance(topic, dict) or not topic.get("id"):
            raise ReachError(NOT_FOUND, f"V2EX topic not found: {topic_id}")
        replies = _get_json(_v2ex_url("/api/replies/show.json", topic_id=topic_id, page=1))
        replies = replies if isinstance(replies, list) else []
        lines = [topic.get("content") or ""]
        for r in replies:
            who = (r.get("member") or {}).get("username", "")
            lines.append(f"\n@{who}: {r.get('content', '')}")
        return [_topic_item(topic, text="\n".join(lines).strip(), raw={"topic": topic, "replies": replies})]

    def _api_user(self, *, username: str, timeout: float) -> list:
        data = _get_json(_v2ex_url("/api/members/show.json", username=username))
        if not isinstance(data, dict) or not data.get("id"):
            raise ReachError(NOT_FOUND, f"V2EX user not found: {username}")
        return [
            make_item(
                title=data.get("username"),
                url=data.get("url"),
                author=data.get("username"),
                published_at=unix_to_iso(data.get("created")),
                text=data.get("bio"),
                raw=data,
            )
        ]

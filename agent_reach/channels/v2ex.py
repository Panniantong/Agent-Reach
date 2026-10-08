# -*- coding: utf-8 -*-
"""V2EX — public API channel for topics, nodes, users, and replies."""

import json
import re
import shutil
import ssl
import subprocess
import urllib.request
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from agent_reach.runtime.result import BAD_INPUT, NOT_FOUND, ReachError, make_item, unix_to_iso
from agent_reach.utils.process import utf8_subprocess_env
from agent_reach.utils.text import scrub_url_credentials

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
    """Fetch JSON, retrying only Python's known TLS EOF via native curl."""
    try:
        return _get_json_with_urllib(url)
    except Exception as exc:
        if isinstance(exc, ssl.SSLCertVerificationError):
            raise
        if not _is_unexpected_tls_eof(exc):
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
    backends = ["V2EX API (public)"]
    tier = 0

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

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "v2ex.com")

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        try:
            _get_json(
                "https://www.v2ex.com/api/topics/show.json?node_name=python&page=1"
            )
            self.active_backend = self.backends[0]
            return "ok", "公开 API 可用（热门主题、节点浏览、主题详情、用户信息）"
        except Exception as e:
            self.active_backend = None
            return (
                "warn",
                f"V2EX API 连接失败（可能需要代理）：{scrub_url_credentials(e)}",
            )

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    def get_hot_topics(self, limit: int = 20) -> list:
        """获取热门帖子列表。

        Returns a list of dicts with keys:
          title, url, replies, node_name, node_title, content
        """
        data = _get_json("https://www.v2ex.com/api/topics/hot.json")
        results = []
        for item in data[:limit]:
            node = item.get("node") or {}
            content = item.get("content", "") or ""
            results.append(
                {
                    "id": item.get("id", 0),
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "replies": item.get("replies", 0),
                    "node_name": node.get("name", ""),
                    "node_title": node.get("title", ""),
                    "content": content[:200],
                    "created": item.get("created", 0),
                }
            )
        return results

    def get_node_topics(self, node_name: str, limit: int = 20) -> list:
        """获取指定节点的最新帖子。

        Args:
            node_name: 节点名称，如 "python"、"tech"、"jobs"
            limit:     最多返回条数

        Returns a list of dicts with keys:
          title, url, replies, node_name, node_title, content
        """
        url = _v2ex_url(
            "/api/topics/show.json",
            node_name=node_name,
            page=1,
        )
        data = _get_json(url)
        results = []
        for item in data[:limit]:
            node = item.get("node") or {}
            content = item.get("content", "") or ""
            results.append(
                {
                    "id": item.get("id", 0),
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "replies": item.get("replies", 0),
                    "node_name": node.get("name", node_name),
                    "node_title": node.get("title", ""),
                    "content": content[:200],
                    "created": item.get("created", 0),
                }
            )
        return results

    def get_topic(self, topic_id: int) -> dict:
        """获取单个帖子详情和回复列表。

        Args:
            topic_id: 帖子 ID（从 URL https://www.v2ex.com/t/<id> 中获取）

        Returns a dict with keys:
          id, title, url, content, replies_count, node_name, node_title,
          author, created, replies (list of dicts with: author, content, created)
        """
        topic_data = _get_json(
            _v2ex_url("/api/topics/show.json", id=topic_id)
        )
        # API returns a list even for single-ID queries
        if isinstance(topic_data, list):
            topic = topic_data[0] if topic_data else {}
        else:
            topic = topic_data

        node = topic.get("node") or {}
        member = topic.get("member") or {}

        # Fetch replies (first page)
        try:
            replies_raw = _get_json(
                _v2ex_url(
                    "/api/replies/show.json",
                    topic_id=topic_id,
                    page=1,
                )
            )
        except Exception:
            replies_raw = []

        replies = [
            {
                "author": (r.get("member") or {}).get("username", ""),
                "content": r.get("content", ""),
                "created": r.get("created", 0),
            }
            for r in (replies_raw or [])
        ]

        return {
            "id": topic.get("id", topic_id),
            "title": topic.get("title", ""),
            "url": topic.get(
                "url",
                f"{_API_BASE}/t/{quote(str(topic_id), safe='')}",
            ),
            "content": topic.get("content", ""),
            "replies_count": topic.get("replies", 0),
            "node_name": node.get("name", ""),
            "node_title": node.get("title", ""),
            "author": member.get("username", ""),
            "created": topic.get("created", 0),
            "replies": replies,
        }

    def get_user(self, username: str) -> dict:
        """获取用户信息。

        Args:
            username: V2EX 用户名

        Returns a dict with keys:
          id, username, url, website, twitter, psn, github, btc,
          location, bio, avatar, created
        """
        data = _get_json(
            _v2ex_url("/api/members/show.json", username=username)
        )
        return {
            "id": data.get("id", 0),
            "username": data.get("username", username),
            "url": data.get(
                "url",
                f"{_API_BASE}/member/{quote(str(username), safe='')}",
            ),
            "website": data.get("website", ""),
            "twitter": data.get("twitter", ""),
            "psn": data.get("psn", ""),
            "github": data.get("github", ""),
            "btc": data.get("btc", ""),
            "location": data.get("location", ""),
            "bio": data.get("bio", ""),
            "avatar": data.get("avatar_large", data.get("avatar_normal", "")),
            "created": data.get("created", 0),
        }

    def search(self, query: str, limit: int = 10) -> list:
        """搜索帖子。

        注意：V2EX 公开 API 暂不支持全文搜索端点（/api/search.json 不可用）。
        本方法通过 Jina Reader 代理 V2EX 站内搜索页面获取结果（纯文本，无结构化数据）。

        如需精确搜索，建议直接访问 https://www.v2ex.com/?q=<query> 或
        使用 Exa channel 的 site:v2ex.com 搜索。

        Returns:
            list of dicts with keys: title, url, snippet
            如果搜索不可用，返回包含单条 {"error": str} 的列表。
        """
        search_url = _v2ex_url("/", q=query)
        return [
            {
                "error": (
                    "V2EX 公开 API 不提供搜索端点。"
                    f"建议改用：{search_url} "
                    "或通过 Exa channel 使用 site:v2ex.com 搜索。"
                )
            }
        ]

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

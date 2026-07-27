# -*- coding: utf-8 -*-
"""V2EX — public API channel for topics, nodes, users, and replies."""

import json
import shutil
import ssl
import subprocess
import urllib.request
from typing import Any

from agent_reach.utils.process import utf8_subprocess_env
from agent_reach.utils.text import scrub_url_credentials

from .base import Channel

_UA = "agent-reach/1.0"
_TIMEOUT = 10
_MAX_RESPONSE_BYTES = 1024 * 1024


def _get_json_with_urllib(url: str) -> Any:
    """Fetch JSON with Python's standard HTTP stack."""
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
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("curl is unavailable for the V2EX TLS fallback")

    command = [
        curl,
        "--fail",
        "--silent",
        "--show-error",
        "--location",
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


class V2EXChannel(Channel):
    name = "v2ex"
    description = "V2EX 节点、主题与回复"
    backends = ["V2EX API (public)"]
    tier = 0

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
        url = (
            f"https://www.v2ex.com/api/topics/show.json"
            f"?node_name={node_name}&page=1"
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
            f"https://www.v2ex.com/api/topics/show.json?id={topic_id}"
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
                f"https://www.v2ex.com/api/replies/show.json"
                f"?topic_id={topic_id}&page=1"
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
            "url": topic.get("url", f"https://www.v2ex.com/t/{topic_id}"),
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
            f"https://www.v2ex.com/api/members/show.json?username={username}"
        )
        return {
            "id": data.get("id", 0),
            "username": data.get("username", username),
            "url": data.get("url", f"https://www.v2ex.com/member/{username}"),
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
        return [
            {
                "error": (
                    "V2EX 公开 API 不提供搜索端点。"
                    f"建议改用：https://www.v2ex.com/?q={query} "
                    "或通过 Exa channel 使用 site:v2ex.com 搜索。"
                )
            }
        ]

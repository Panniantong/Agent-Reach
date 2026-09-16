# -*- coding: utf-8 -*-
"""Hacker News — official Firebase API + Algolia search, both public.

Routing is deliberately mixed — each operation rides the endpoint whose
shape fits best:
  - story lists (top/new/best/ask/show/job) → Firebase /v0/<kind>stories.json
  - item detail with the full comment tree   → Algolia /api/v1/items/:id
    (one request returns the whole nested tree; Firebase would need 1+N
    per-comment requests for the same view)
  - full-text search                         → Algolia /api/v1/search
  - user profile                             → Firebase /v0/user/:name.json

Both APIs are keyless, read-only, and return structured JSON — zero config.
"""

import json
import urllib.request
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from agent_reach.utils.text import scrub_url_credentials

from .base import Channel

_UA = "agent-reach/1.0"
_TIMEOUT = 10
_MAX_RESPONSE_BYTES = 1024 * 1024

_FIREBASE_BASE = "https://hacker-news.firebaseio.com/v0"
_ALGOLIA_BASE = "https://hn.algolia.com/api/v1"

_STORY_KINDS = ("top", "new", "best", "ask", "show", "job")


def _validate_api_url(url: str) -> None:
    """Allow only the two public Hacker News HTTPS JSON APIs."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid Hacker News API URL") from exc
    host = (parsed.hostname or "").lower()
    firebase_ok = (
        host == "hacker-news.firebaseio.com"
        and port in {None, 443}
        and parsed.path.startswith("/v0/")
    )
    algolia_ok = (
        host == "hn.algolia.com" and port in {None, 443} and parsed.path.startswith("/api/")
    )
    if (
        parsed.scheme.lower() != "https"
        or not (firebase_ok or algolia_ok)
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("only the Hacker News HTTPS APIs are allowed")


def _path_segment(value: Any) -> str:
    """Encode a caller value as a single safe path segment."""
    return quote(str(value), safe="")


def _get_json(url: str) -> Any:
    """Fetch JSON from a validated Hacker News API URL."""
    _validate_api_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        raw = resp.read(_MAX_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError("Hacker News API response exceeds the 1 MiB safety limit")
    return json.loads(raw.decode("utf-8"))


class HackerNewsChannel(Channel):
    name = "hackernews"
    description = "Hacker News 帖子、评论、用户与搜索"
    backends = ["Hacker News API (public)"]
    tier = 0

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "news.ycombinator.com")

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        try:
            # maxitem.json returns a single integer — the smallest real probe
            _get_json(f"{_FIREBASE_BASE}/maxitem.json")
            self.active_backend = self.backends[0]
            return (
                "ok",
                "公开 API 可用（热门/最新/Ask/Show/Jobs 列表、帖子详情+评论树、"
                "用户信息、全文搜索）",
            )
        except Exception as e:
            self.active_backend = None
            return (
                "warn",
                f"Hacker News API 连接失败（可能需要代理）：{scrub_url_credentials(e)}",
            )

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    @staticmethod
    def _story_summary(item: dict) -> dict:
        """Reshape a Firebase story item into the uniform list entry."""
        item_id = item.get("id", 0)
        return {
            "id": item_id,
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "hn_url": f"https://news.ycombinator.com/item?id={item_id}",
            "score": item.get("score", 0),
            "comments": item.get("descendants", 0),
            "author": item.get("by", ""),
            "time": item.get("time", 0),
            # Ask/Show HN 正文是 HTML，与 V2EX 一致只保留前 200 字符预览
            "text": (item.get("text") or "")[:200],
        }

    def get_stories(self, kind: str = "top", limit: int = 20) -> list:
        """获取帖子列表。

        Args:
            kind:  列表类型 — top / new / best / ask / show / job
            limit: 最多返回条数（每条一次 item 请求，建议 ≤30）

        Returns a list of dicts with keys:
          id, title, url, hn_url, score, comments, author, time, text
        """
        if kind not in _STORY_KINDS:
            raise ValueError(f"unknown story kind {kind!r}; expected one of {_STORY_KINDS}")
        ids = _get_json(f"{_FIREBASE_BASE}/{kind}stories.json") or []
        results = []
        for item_id in ids[: max(0, limit)]:
            try:
                item = _get_json(f"{_FIREBASE_BASE}/item/{_path_segment(item_id)}.json")
            except Exception:
                continue  # 单条拉取失败不拖垮整个列表
            if not item:
                continue  # 已删除的 item，Firebase 返回 null
            results.append(self._story_summary(item))
        return results

    def get_item(self, item_id: int) -> dict:
        """获取单个帖子详情和完整评论树。

        走 Algolia items 端点：单次请求即返回嵌套评论树，避免 Firebase
        逐评论拉取的 1+N 问题。

        Args:
            item_id: 帖子 ID（从 URL news.ycombinator.com/item?id=<id> 获取）

        Returns a dict with keys:
          id, title, url, hn_url, author, points, comments, created_at,
          text, comments_tree（每条: id, author, text, created_at, depth,
          children）
        """
        data = _get_json(f"{_ALGOLIA_BASE}/items/{_path_segment(item_id)}")
        if not data:
            raise ValueError(f"Hacker News item not found: {item_id}")
        comments: list = []
        self._collect_comments(data.get("children") or [], 0, comments)
        story_id = data.get("id", item_id)
        return {
            "id": story_id,
            "title": data.get("title", ""),
            "url": data.get("url", ""),
            "hn_url": f"https://news.ycombinator.com/item?id={story_id}",
            "author": data.get("author", ""),
            "points": data.get("points", 0),
            "comments": data.get("num_comments", len(comments)),
            "created_at": data.get("created_at", ""),
            "text": data.get("story_text") or data.get("comment_text") or "",
            "comments_tree": comments,
        }

    def _collect_comments(self, children: list, depth: int, out: list) -> None:
        """Flatten Algolia's nested comment tree depth-first."""
        for node in children:
            if not isinstance(node, dict):
                continue
            out.append(
                {
                    "id": node.get("id", 0),
                    "author": node.get("author", ""),
                    "text": node.get("text") or "",
                    "created_at": node.get("created_at", ""),
                    "depth": depth,
                    "children": len(node.get("children") or []),
                }
            )
            self._collect_comments(node.get("children") or [], depth + 1, out)

    def get_user(self, username: str) -> dict:
        """获取用户信息。

        Args:
            username: Hacker News 用户名

        Returns a dict with keys:
          username, karma, about, created, submitted, hn_url
        """
        data = _get_json(f"{_FIREBASE_BASE}/user/{_path_segment(username)}.json")
        if not data:
            raise ValueError(f"Hacker News user not found: {username}")
        return {
            "username": data.get("id", username),
            "karma": data.get("karma", 0),
            "about": data.get("about", ""),
            "created": data.get("created", 0),
            "submitted": data.get("submitted") or [],
            "hn_url": (
                f"https://news.ycombinator.com/user?id={_path_segment(data.get('id', username))}"
            ),
        }

    def search(self, query: str, limit: int = 10, tags: str = "story") -> list:
        """全文搜索（Algolia，免 key）。

        Args:
            query: 搜索词
            limit: 最多返回条数
            tags:  过滤标签 — story（默认）/ comment / ask_hn / show_hn /
                   front_page；留空搜索全部

        Returns a list of dicts with keys:
          id, title, url, hn_url, author, points, comments, created_at,
          snippet
        """
        params = urlencode(
            {"query": query, "hitsPerPage": max(1, limit), **({"tags": tags} if tags else {})}
        )
        data = _get_json(f"{_ALGOLIA_BASE}/search?{params}")
        results = []
        for hit in (data.get("hits") or [])[: max(1, limit)]:
            object_id = hit.get("objectID", "")
            snippet = hit.get("story_text") or hit.get("comment_text") or hit.get("title") or ""
            results.append(
                {
                    "id": object_id,
                    # comment 命中只有 story_title/story_url
                    "title": hit.get("title") or hit.get("story_title") or "",
                    "url": hit.get("url") or hit.get("story_url") or "",
                    "hn_url": (f"https://news.ycombinator.com/item?id={_path_segment(object_id)}"),
                    "author": hit.get("author", ""),
                    "points": hit.get("points") or hit.get("story_points") or 0,
                    "comments": hit.get("num_comments") or 0,
                    "created_at": hit.get("created_at_i", 0),
                    "snippet": snippet[:200],
                }
            )
        return results

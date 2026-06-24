# -*- coding: utf-8 -*-
"""Hacker News — public API channel for stories, comments, users, and search.

Two zero-config official APIs, no key required:
  - Firebase API (https://hacker-news.firebaseio.com/v0/) for stories, items,
    comments, and user profiles.
  - Algolia HN Search API (https://hn.algolia.com/api/v1/) for full-text search,
    since the Firebase API has no search endpoint.
"""

import json
import urllib.parse
import urllib.request
from typing import Any

from .base import Channel

_UA = "agent-reach/1.0"
_TIMEOUT = 10

_FIREBASE = "https://hacker-news.firebaseio.com/v0"
_ALGOLIA = "https://hn.algolia.com/api/v1"

# Story-list endpoints exposed by the Firebase API, keyed by a short kind name.
_STORY_LISTS = {
    "top": "topstories",
    "new": "newstories",
    "best": "beststories",
    "ask": "askstories",
    "show": "showstories",
    "job": "jobstories",
}


def _get_json(url: str) -> Any:
    """Fetch *url* and return parsed JSON. Raises on HTTP/network errors."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _item_url(item_id: int) -> str:
    """Canonical web URL for a Hacker News item."""
    return f"https://news.ycombinator.com/item?id={item_id}"


class HackerNewsChannel(Channel):
    name = "hackernews"
    description = "Hacker News 热门/新/最佳故事、评论、用户与全文搜索"
    backends = ["Hacker News API (public)", "Algolia HN Search (public)"]
    tier = 0

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "news.ycombinator.com" in d

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        try:
            # maxitem.json is the cheapest probe — a single integer, no list walk.
            _get_json(f"{_FIREBASE}/maxitem.json")
            self.active_backend = self.backends[0]
            return "ok", "公开 API 可用（热门/新/最佳故事、评论、用户、全文搜索）"
        except Exception as e:
            self.active_backend = None
            return "warn", f"Hacker News API 连接失败（可能需要代理）：{e}"

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    def _format_story(self, item: dict) -> dict:
        """Normalize a Firebase story/job item into a flat dict."""
        text = item.get("text", "") or ""
        return {
            "id": item.get("id", 0),
            "title": item.get("title", ""),
            # External link for link posts; falls back to the HN discussion page
            # for Ask HN / text posts that carry no `url`.
            "url": item.get("url", "") or _item_url(item.get("id", 0)),
            "hn_url": _item_url(item.get("id", 0)),
            "score": item.get("score", 0),
            "by": item.get("by", ""),
            "comments": item.get("descendants", 0),
            "type": item.get("type", "story"),
            "text": text[:200],
            "created": item.get("time", 0),
        }

    def get_stories(self, kind: str = "top", limit: int = 20) -> list:
        """获取故事列表。

        Args:
            kind:  one of "top", "new", "best", "ask", "show", "job"
            limit: 最多返回条数

        Returns a list of dicts with keys:
          id, title, url, hn_url, score, by, comments, type, text, created
        """
        endpoint = _STORY_LISTS.get(kind)
        if endpoint is None:
            raise ValueError(
                f"unknown kind {kind!r}; expected one of {sorted(_STORY_LISTS)}"
            )
        ids = _get_json(f"{_FIREBASE}/{endpoint}.json") or []
        results = []
        for item_id in ids[:limit]:
            try:
                item = _get_json(f"{_FIREBASE}/item/{item_id}.json")
            except Exception:
                continue
            if item:
                results.append(self._format_story(item))
        return results

    def get_top_stories(self, limit: int = 20) -> list:
        """获取首页热门故事（top stories）。见 get_stories()。"""
        return self.get_stories("top", limit)

    def get_item(self, item_id: int, comment_limit: int = 20) -> dict:
        """获取单个故事详情和顶层评论。

        Args:
            item_id:       item ID（从 URL https://news.ycombinator.com/item?id=<id> 获取）
            comment_limit: 最多返回的顶层评论条数

        Returns a dict with keys:
          id, title, url, hn_url, by, score, comments, type, text, created,
          replies (list of dicts with: id, by, text, created)
        """
        item = _get_json(f"{_FIREBASE}/item/{item_id}.json") or {}

        replies = []
        for kid in (item.get("kids") or [])[:comment_limit]:
            try:
                c = _get_json(f"{_FIREBASE}/item/{kid}.json")
            except Exception:
                continue
            if not c or c.get("deleted") or c.get("dead"):
                continue
            replies.append(
                {
                    "id": c.get("id", kid),
                    "by": c.get("by", ""),
                    "text": c.get("text", ""),
                    "created": c.get("time", 0),
                }
            )

        return {
            "id": item.get("id", item_id),
            "title": item.get("title", ""),
            "url": item.get("url", "") or _item_url(item_id),
            "hn_url": _item_url(item_id),
            "by": item.get("by", ""),
            "score": item.get("score", 0),
            "comments": item.get("descendants", 0),
            "type": item.get("type", "story"),
            "text": item.get("text", ""),
            "created": item.get("time", 0),
            "replies": replies,
        }

    def get_user(self, username: str) -> dict:
        """获取用户信息。

        Args:
            username: Hacker News 用户名

        Returns a dict with keys:
          id, url, karma, created, about, submitted_count
        """
        data = _get_json(f"{_FIREBASE}/user/{username}.json") or {}
        return {
            "id": data.get("id", username),
            "url": f"https://news.ycombinator.com/user?id={username}",
            "karma": data.get("karma", 0),
            "created": data.get("created", 0),
            "about": data.get("about", ""),
            "submitted_count": len(data.get("submitted", []) or []),
        }

    def search(self, query: str, limit: int = 10, by_date: bool = False) -> list:
        """全文搜索故事（通过 Algolia HN Search API）。

        Args:
            query:   搜索关键词
            limit:   最多返回条数
            by_date: True 按时间排序（最新优先），False 按相关性排序（默认）

        Returns a list of dicts with keys:
          id, title, url, hn_url, by, score, comments, created
        """
        endpoint = "search_by_date" if by_date else "search"
        params = urllib.parse.urlencode(
            {"query": query, "tags": "story", "hitsPerPage": limit}
        )
        data = _get_json(f"{_ALGOLIA}/{endpoint}?{params}")
        results = []
        for hit in (data.get("hits") or [])[:limit]:
            object_id = hit.get("objectID", "")
            results.append(
                {
                    "id": object_id,
                    "title": hit.get("title", "") or hit.get("story_title", ""),
                    "url": hit.get("url", "") or _item_url(object_id),
                    "hn_url": _item_url(object_id),
                    "by": hit.get("author", ""),
                    "score": hit.get("points", 0) or 0,
                    "comments": hit.get("num_comments", 0) or 0,
                    "created": hit.get("created_at_i", 0),
                }
            )
        return results

# -*- coding: utf-8 -*-
"""Lobsters — public API channel for stories, tags, comments, and users.

Lobsters (lobste.rs) is a focused computing-oriented community. It exposes a
zero-config public JSON API (append `.json` to most pages), no key required.

Note: Lobsters has no JSON search endpoint (`search.json` returns 400), so
`search()` returns guidance toward the site search / Exa instead — mirroring
the V2EX channel's behavior.
"""

import json
import urllib.request
from typing import Any

from .base import Channel

_UA = "agent-reach/1.0"
_TIMEOUT = 10
_BASE = "https://lobste.rs"

# Story-list endpoints keyed by a short kind name.
_STORY_LISTS = {
    "hottest": "hottest",
    "newest": "newest",
}


def _get_json(url: str) -> Any:
    """Fetch *url* and return parsed JSON. Raises on HTTP/network errors."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


class LobstersChannel(Channel):
    name = "lobsters"
    description = "Lobsters 技术社区 热门/最新故事、标签、评论与用户"
    backends = ["Lobsters API (public)"]
    tier = 0

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "lobste.rs" in d

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        try:
            _get_json(f"{_BASE}/hottest.json")
            self.active_backend = self.backends[0]
            return "ok", "公开 API 可用（热门/最新故事、标签、评论、用户）"
        except Exception as e:
            self.active_backend = None
            return "warn", f"Lobsters API 连接失败（可能需要代理）：{e}"

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    def _format_story(self, item: dict) -> dict:
        """Normalize a Lobsters story into a flat dict."""
        short_id = item.get("short_id", "")
        discussion = item.get("short_id_url", f"{_BASE}/s/{short_id}")
        description = item.get("description_plain") or item.get("description") or ""
        return {
            "short_id": short_id,
            "title": item.get("title", ""),
            # External link for link posts; falls back to the discussion page
            # for text/Ask posts that carry no `url`.
            "url": item.get("url", "") or discussion,
            "comments_url": discussion,
            "score": item.get("score", 0),
            "by": item.get("submitter_user", ""),
            "comments": item.get("comment_count", 0),
            "tags": item.get("tags", []) or [],
            "description": description[:200],
            "created": item.get("created_at", ""),
        }

    def get_stories(self, kind: str = "hottest", limit: int = 20) -> list:
        """获取故事列表。

        Args:
            kind:  "hottest" 或 "newest"
            limit: 最多返回条数

        Returns a list of dicts with keys:
          short_id, title, url, comments_url, score, by, comments, tags,
          description, created
        """
        endpoint = _STORY_LISTS.get(kind)
        if endpoint is None:
            raise ValueError(
                f"unknown kind {kind!r}; expected one of {sorted(_STORY_LISTS)}"
            )
        data = _get_json(f"{_BASE}/{endpoint}.json") or []
        return [self._format_story(item) for item in data[:limit]]

    def get_hottest(self, limit: int = 20) -> list:
        """获取热门故事。见 get_stories()。"""
        return self.get_stories("hottest", limit)

    def get_newest(self, limit: int = 20) -> list:
        """获取最新故事。见 get_stories()。"""
        return self.get_stories("newest", limit)

    def get_tag(self, tag: str, limit: int = 20) -> list:
        """获取指定标签下的故事。

        Args:
            tag:   标签名，如 "rust"、"python"、"security"、"ai"
            limit: 最多返回条数

        Returns a list of dicts (same shape as get_stories()).
        """
        data = _get_json(f"{_BASE}/t/{tag}.json") or []
        return [self._format_story(item) for item in data[:limit]]

    def get_story(self, short_id: str, comment_limit: int = 50) -> dict:
        """获取单个故事详情和评论。

        Args:
            short_id:      故事短 ID（从 URL https://lobste.rs/s/<short_id> 获取）
            comment_limit: 最多返回的评论条数

        Returns a dict with keys:
          short_id, title, url, comments_url, score, by, comments, tags,
          description, created, replies (list of dicts with:
          by, text, score, depth, created)
        """
        item = _get_json(f"{_BASE}/s/{short_id}.json") or {}
        story = self._format_story(item)

        replies = []
        for c in (item.get("comments") or [])[:comment_limit]:
            if c.get("is_deleted"):
                continue
            replies.append(
                {
                    "by": c.get("commenting_user", ""),
                    "text": c.get("comment_plain") or c.get("comment") or "",
                    "score": c.get("score", 0),
                    "depth": c.get("depth", 0),
                    "created": c.get("created_at", ""),
                }
            )
        story["replies"] = replies
        return story

    def get_user(self, username: str) -> dict:
        """获取用户信息。

        Args:
            username: Lobsters 用户名

        Returns a dict with keys:
          username, url, karma, created, about, github_username,
          is_admin, is_moderator
        """
        # Lobsters serves user JSON at /~<username>.json (the /u/ form redirects).
        data = _get_json(f"{_BASE}/~{username}.json") or {}
        return {
            "username": data.get("username", username),
            "url": f"{_BASE}/~{username}",
            "karma": data.get("karma", 0),
            "created": data.get("created_at", ""),
            "about": data.get("about", ""),
            "github_username": data.get("github_username", ""),
            "is_admin": data.get("is_admin", False),
            "is_moderator": data.get("is_moderator", False),
        }

    def search(self, query: str, limit: int = 10) -> list:
        """搜索故事。

        注意：Lobsters 公开 API 不提供 JSON 搜索端点（`search.json` 返回 400）。
        建议直接访问站内搜索页，或通过 Exa channel 使用 site:lobste.rs 搜索。

        Returns:
            list of a single {"error": str} dict pointing at usable alternatives.
        """
        return [
            {
                "error": (
                    "Lobsters 公开 API 不提供 JSON 搜索端点。"
                    f"建议改用：https://lobste.rs/search?q={query}&what=stories "
                    "或通过 Exa channel 使用 site:lobste.rs 搜索。"
                )
            }
        ]

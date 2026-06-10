# -*- coding: utf-8 -*-
"""Xquik — X/Twitter search, tweet lookup, user profiles & trends via API key."""

import json
import os
import urllib.parse
import urllib.request
from typing import Any

from .base import Channel

_BASE = "https://xquik.com/api/v1"
_UA = "agent-reach/1.0"
_TIMEOUT = 15


def _get_api_key() -> str:
    """Return the Xquik API key from env or empty string."""
    return os.environ.get("XQUIK_API_KEY", "")


def _get_json(path: str, params: dict[str, Any] | None = None) -> Any:
    """Fetch *path* from the Xquik API and return parsed JSON.

    Raises urllib.error.HTTPError on non-2xx or ValueError on bad JSON.
    """
    api_key = _get_api_key()
    url = f"{_BASE}{path}"
    if params:
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{url}?{qs}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "X-API-Key": api_key,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


class XquikChannel(Channel):
    name = "xquik"
    description = "X/Twitter 搜索、推文、用户与趋势（API Key）"
    backends = ["Xquik API"]
    tier = 1

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        d = urllib.parse.urlparse(url).netloc.lower()
        return "x.com" in d or "twitter.com" in d

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        api_key = _get_api_key()
        if not api_key:
            return "off", (
                "Xquik API Key 未配置。获取方式：\n"
                "  1. 注册 https://xquik.com\n"
                '  2. 设置环境变量：export XQUIK_API_KEY="xk_your_key"'
            )
        try:
            data = _get_json("/trends", {"count": 1})
            if data.get("trends"):
                return "ok", (
                    "Xquik API 可用（搜索推文、用户查询、趋势，"
                    "含互动数据：点赞/转发/回复/引用/浏览/收藏）"
                )
            return "warn", "Xquik API Key 有效但返回数据为空"
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return "warn", (
                    "Xquik API Key 无效或过期。请检查：https://xquik.com/dashboard/api-keys"
                )
            return "warn", f"Xquik API 连接失败（HTTP {e.code}）"
        except Exception as e:
            return "warn", f"Xquik API 连接失败：{e}"

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    def search_tweets(
        self,
        query: str,
        limit: int = 20,
        query_type: str = "Latest",
        cursor: str | None = None,
    ) -> dict:
        """搜索推文。

        支持 X 搜索语法：关键词、#标签、from:用户、"精确匹配"、
        since:YYYY-MM-DD、until:YYYY-MM-DD、min_faves:N。

        Args:
            query:      搜索关键词
            limit:      最多返回条数（上限 200）
            query_type: "Latest"（最新）或 "Top"（热门）
            cursor:     分页游标（来自上一次响应的 next_cursor）

        Returns a dict with keys:
          tweets (list), has_next_page (bool), next_cursor (str|None)

        Each tweet dict contains:
          id, text, createdAt, likeCount, retweetCount, replyCount,
          quoteCount, viewCount, bookmarkCount,
          author: {id, username, name, verified}
        """
        data = _get_json(
            "/x/tweets/search",
            {
                "q": query,
                "limit": min(limit, 200),
                "queryType": query_type,
                "cursor": cursor,
            },
        )
        return {
            "tweets": data.get("tweets", []),
            "has_next_page": data.get("has_next_page", False),
            "next_cursor": data.get("next_cursor"),
        }

    def get_tweet(self, tweet_id: str) -> dict:
        """获取单条推文详情。

        Args:
            tweet_id: 推文 ID（数字字符串，或完整 URL 中的 ID 部分）

        Returns a dict with keys:
          id, text, createdAt, likeCount, retweetCount, replyCount,
          quoteCount, viewCount, bookmarkCount, type, source, media,
          author: {id, username, name, followers, verified, profilePicture}
        """
        return _get_json(f"/x/tweets/{tweet_id}")

    def search_users(self, query: str, cursor: str | None = None) -> dict:
        """搜索用户。

        Args:
            query:  用户名或显示名搜索
            cursor: 分页游标

        Returns a dict with keys:
          users (list), has_next_page (bool), next_cursor (str|None)

        Each user dict contains:
          id, username, name, description, followers, following,
          verified, profilePicture, location, createdAt, statusesCount
        """
        data = _get_json(
            "/x/users/search",
            {"q": query, "cursor": cursor},
        )
        return {
            "users": data.get("users", []),
            "has_next_page": data.get("has_next_page", False),
            "next_cursor": data.get("next_cursor"),
        }

    def get_user(self, username: str) -> dict:
        """获取用户资料。

        Args:
            username: X 用户名（不含 @）或数字 ID

        Returns a dict with keys:
          id, username, name, description, followers, following,
          verified, profilePicture, location, createdAt, statusesCount
        """
        return _get_json(f"/x/users/{username}")

    def get_trends(self, woeid: int = 1, count: int = 30) -> list:
        """获取热门趋势。

        Args:
            woeid: 地区 WOEID（1=全球，23424977=美国，23424975=英国，
                   23424969=土耳其，23424781=日本，23424756=中国台湾）
            count: 返回条数（上限 50）

        Returns a list of dicts with keys:
          name, description, query, rank
        """
        data = _get_json("/trends", {"woeid": woeid, "count": min(count, 50)})
        return data.get("trends", [])

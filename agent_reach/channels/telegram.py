# -*- coding: utf-8 -*-
"""Telegram — public channel reader via t.me/s/ web preview."""

import json
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

from .base import Channel

_UA = "agent-reach/1.0"
_TIMEOUT = 15


# ------------------------------------------------------------------ #
# HTML parser for t.me/s/ channel preview pages
# ------------------------------------------------------------------ #

class _TelegramPostParser(HTMLParser):
    """Minimal parser that extracts message texts from t.me/s/<channel>.

    Telegram's public channel preview pages wrap each message body in
    ``<div class="tgme_widget_message_text ...">...</div>``.
    This parser collects the text content of those divs.
    """

    def __init__(self) -> None:
        super().__init__()
        self._in_message = False
        self._depth = 0
        self._current_text: List[str] = []
        self.posts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag == "div":
            cls = dict(attrs).get("class", "")
            if "tgme_widget_message_text" in cls:
                self._in_message = True
                self._depth = 1
                self._current_text = []
                return
        if self._in_message and tag == "div":
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._in_message and tag == "div":
            self._depth -= 1
            if self._depth <= 0:
                self.posts.append("".join(self._current_text).strip())
                self._in_message = False
                self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._in_message:
            self._current_text.append(data)


class _TelegramPostIdParser(HTMLParser):
    """Extract post IDs (data-post attributes) from message wrappers.

    Each message widget has ``<div class="tgme_widget_message_wrap" ...>``
    containing ``<div class="tgme_widget_message" data-post="channel/123">``.
    """

    def __init__(self) -> None:
        super().__init__()
        self.post_ids: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag == "div":
            attr_dict = dict(attrs)
            cls = attr_dict.get("class", "")
            if "tgme_widget_message " in cls or cls.strip().endswith("tgme_widget_message"):
                data_post = attr_dict.get("data-post", "")
                if data_post:
                    self.post_ids.append(data_post)


def _get_html(url: str) -> str:
    """Fetch *url* and return raw HTML text. Raises on HTTP/network errors."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.read().decode("utf-8")


def _jina_read(url: str) -> str:
    """Read *url* through Jina Reader, returning Markdown text."""
    jina_url = f"https://r.jina.ai/{url}"
    req = urllib.request.Request(
        jina_url,
        headers={"User-Agent": _UA, "Accept": "text/plain"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


class TelegramChannel(Channel):
    name = "telegram"
    description = "Telegram 公开频道阅读"
    backends = ["Telegram Web Preview", "Jina Reader"]
    tier = 0

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "t.me" in d or "telegram.me" in d

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None) -> Tuple[str, str]:
        """Probe Telegram web preview via Pavel Durov's public channel."""
        try:
            html = _get_html("https://t.me/s/durov")
            if "tgme_widget_message" in html:
                self.active_backend = self.backends[0]
                return "ok", "公开频道预览可用（t.me/s/ HTML 解析，无需 API Key）"
        except Exception:
            pass

        # Fallback: Jina Reader
        try:
            text = _jina_read("https://t.me/s/durov")
            if text and len(text) > 100:
                self.active_backend = self.backends[1]
                return "ok", "通过 Jina Reader 可读取公开频道（HTML 直连不可用）"
        except Exception:
            pass

        self.active_backend = None
        return "warn", "Telegram 公开频道不可达（可能需要代理）"

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    def read_channel(self, channel_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """获取公开频道的最新帖子。

        Fetches recent posts from a public Telegram channel by parsing
        the ``t.me/s/<channel_name>`` HTML preview page.

        Args:
            channel_name: Channel username (without @), e.g. "durov"
            limit:        Maximum number of posts to return

        Returns:
            List of dicts with keys: post_id, text, url
        """
        channel_name = channel_name.lstrip("@")
        url = f"https://t.me/s/{channel_name}"
        html = _get_html(url)

        # Parse post texts
        text_parser = _TelegramPostParser()
        text_parser.feed(html)

        # Parse post IDs
        id_parser = _TelegramPostIdParser()
        id_parser.feed(html)

        results: List[Dict[str, Any]] = []
        posts = text_parser.posts
        post_ids = id_parser.post_ids

        # Align texts and IDs (both lists are in DOM order)
        count = min(len(posts), len(post_ids), limit)
        for i in range(count):
            data_post = post_ids[i]  # e.g. "durov/123"
            post_id = data_post.split("/")[-1] if "/" in data_post else data_post
            results.append({
                "post_id": post_id,
                "text": posts[i][:500],
                "url": f"https://t.me/{channel_name}/{post_id}",
            })

        # If no IDs parsed, return texts only
        if not results and posts:
            for i, text in enumerate(posts[:limit]):
                results.append({
                    "post_id": str(i),
                    "text": text[:500],
                    "url": url,
                })

        # Return newest first (page is chronological, newest at bottom)
        results.reverse()
        return results[:limit]

    def read_post(self, channel_name: str, post_id: int) -> Dict[str, Any]:
        """获取单条帖子内容（通过 Jina Reader）。

        Args:
            channel_name: Channel username (without @), e.g. "durov"
            post_id:      Numeric post ID

        Returns:
            Dict with keys: post_id, channel, url, content
        """
        channel_name = channel_name.lstrip("@")
        url = f"https://t.me/{channel_name}/{post_id}"
        content = _jina_read(url)
        return {
            "post_id": str(post_id),
            "channel": channel_name,
            "url": url,
            "content": content,
        }

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """搜索 Telegram 公开内容。

        注意：Telegram 没有公开搜索 API。
        建议使用 Exa channel 的 site:t.me 搜索获取更好的结果。

        Returns:
            List containing a single dict with an error/suggestion message.
        """
        return [
            {
                "error": (
                    "Telegram 没有公开搜索 API。"
                    f"建议改用 Exa channel 搜索：site:t.me {query}"
                )
            }
        ]

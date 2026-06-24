# -*- coding: utf-8 -*-
"""Wikipedia — public API channel for search, summaries, and full articles.

Two zero-config official Wikimedia APIs, no key required:
  - REST API (https://<lang>.wikipedia.org/api/rest_v1/) for page summaries.
  - MediaWiki Action API (https://<lang>.wikipedia.org/w/api.php) for full-text
    search, plain-text article extracts, and section listings.

Multi-language: every method takes a `lang` argument (the Wikipedia subdomain,
e.g. "en", "zh", "ja", "de"); it defaults to "en".
"""

import html
import json
import re
import urllib.parse
import urllib.request
from typing import Any

from .base import Channel

_UA = "agent-reach/1.0"
_TIMEOUT = 10

_TAG_RE = re.compile(r"<[^>]+>")


def _get_json(url: str) -> Any:
    """Fetch *url* and return parsed JSON. Raises on HTTP/network errors."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _strip_html(text: str) -> str:
    """Drop HTML tags and unescape entities (search snippets come wrapped in
    <span> highlights and contain entities like &quot; / &#039;)."""
    return html.unescape(_TAG_RE.sub("", text or ""))


def _api_base(lang: str) -> str:
    return f"https://{lang}.wikipedia.org/w/api.php"


def _rest_base(lang: str) -> str:
    return f"https://{lang}.wikipedia.org/api/rest_v1"


def _page_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"


class WikipediaChannel(Channel):
    name = "wikipedia"
    description = "维基百科 全文搜索、词条摘要、正文与章节（多语言）"
    backends = ["Wikimedia REST API (public)", "MediaWiki Action API (public)"]
    tier = 0

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "wikipedia.org" in d

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        try:
            # siteinfo is a tiny, cache-friendly probe.
            _get_json(
                f"{_api_base('en')}?action=query&meta=siteinfo&format=json"
            )
            self.active_backend = self.backends[0]
            return "ok", "公开 API 可用（全文搜索、词条摘要、正文、章节，多语言）"
        except Exception as e:
            self.active_backend = None
            return "warn", f"Wikipedia API 连接失败（可能需要代理）：{e}"

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    def search(self, query: str, limit: int = 10, lang: str = "en") -> list:
        """全文搜索词条。

        Args:
            query: 搜索关键词
            limit: 最多返回条数
            lang:  Wikipedia 语言（子域名），如 "en"、"zh"、"ja"

        Returns a list of dicts with keys:
          title, url, snippet, pageid, wordcount
        """
        params = urllib.parse.urlencode(
            {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": limit,
                "format": "json",
            }
        )
        data = _get_json(f"{_api_base(lang)}?{params}")
        hits = ((data.get("query") or {}).get("search")) or []
        results = []
        for hit in hits[:limit]:
            title = hit.get("title", "")
            results.append(
                {
                    "title": title,
                    "url": _page_url(lang, title),
                    "snippet": _strip_html(hit.get("snippet", "")),
                    "pageid": hit.get("pageid", 0),
                    "wordcount": hit.get("wordcount", 0),
                }
            )
        return results

    def get_summary(self, title: str, lang: str = "en") -> dict:
        """获取词条摘要（含简介段落、描述、缩略图）。

        Args:
            title: 词条标题
            lang:  Wikipedia 语言（子域名）

        Returns a dict with keys:
          title, description, extract, url, thumbnail, lang
        """
        quoted = urllib.parse.quote(title.replace(" ", "_"))
        data = _get_json(f"{_rest_base(lang)}/page/summary/{quoted}")
        content_urls = (data.get("content_urls") or {}).get("desktop") or {}
        thumbnail = (data.get("thumbnail") or {}).get("source", "")
        return {
            "title": data.get("title", title),
            "description": data.get("description", ""),
            "extract": data.get("extract", ""),
            "url": content_urls.get("page", _page_url(lang, title)),
            "thumbnail": thumbnail,
            "lang": data.get("lang", lang),
        }

    def get_article(self, title: str, lang: str = "en") -> dict:
        """获取词条正文（纯文本全文）。

        Args:
            title: 词条标题
            lang:  Wikipedia 语言（子域名）

        Returns a dict with keys:
          title, extract, url, pageid
        """
        params = urllib.parse.urlencode(
            {
                "action": "query",
                "prop": "extracts",
                "titles": title,
                "explaintext": 1,
                "redirects": 1,
                "format": "json",
            }
        )
        data = _get_json(f"{_api_base(lang)}?{params}")
        pages = (data.get("query") or {}).get("pages") or {}
        page: dict = next(iter(pages.values()), {}) if pages else {}
        return {
            "title": page.get("title", title),
            "extract": page.get("extract", ""),
            "url": _page_url(lang, page.get("title", title)),
            "pageid": page.get("pageid", 0),
        }

    def get_sections(self, title: str, lang: str = "en") -> list:
        """获取词条章节目录。

        Args:
            title: 词条标题
            lang:  Wikipedia 语言（子域名）

        Returns a list of dicts with keys:
          index, level, title, anchor
        """
        params = urllib.parse.urlencode(
            {
                "action": "parse",
                "page": title,
                "prop": "sections",
                "redirects": 1,
                "format": "json",
            }
        )
        data = _get_json(f"{_api_base(lang)}?{params}")
        sections = (data.get("parse") or {}).get("sections") or []
        return [
            {
                "index": s.get("index", ""),
                "level": s.get("level", ""),
                "title": s.get("line", ""),
                "anchor": s.get("anchor", ""),
            }
            for s in sections
        ]

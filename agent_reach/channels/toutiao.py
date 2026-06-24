# -*- coding: utf-8 -*-
"""Toutiao (今日头条) — search articles and trending content."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Tuple

from .base import Channel

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_TIMEOUT_SEARCH = 22.0
_TIMEOUT_READ = 30.0
_SEARCH_ATTEMPTS = 3
_READ_ATTEMPTS = 3
_SEARCH_URL = (
    "https://so.toutiao.com/search"
    "?dvpf=pc&source=input&keyword={keyword}&enable_druid_v2=1"
)

_SKIP_TEMPLATES = ("Search", "Bottom", "76-", "20-", "26-", "67-baike")


def _should_retry_http(err: urllib.error.HTTPError) -> bool:
    code = getattr(err, "code", 0) or 0
    return code == 429 or code >= 500


def _request_body(
    url: str,
    *,
    headers: Dict[str, str],
    timeout: float,
    attempts: int,
) -> bytes:
    """GET url with retries on transient network / server errors."""
    last_exc: BaseException | None = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_exc = e
            if _should_retry_http(e) and i < attempts - 1:
                time.sleep(0.4 * (2**i))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_exc = e
            if i < attempts - 1:
                time.sleep(0.4 * (2**i))
                continue
            raise
    assert last_exc is not None
    raise last_exc


def _fetch_html(url: str) -> str:
    data = _request_body(
        url,
        headers={"User-Agent": _UA},
        timeout=_TIMEOUT_SEARCH,
        attempts=_SEARCH_ATTEMPTS,
    )
    return data.decode("utf-8", errors="replace")


def _parse_search_results(html: str) -> list:
    """Extract article results from Toutiao search page HTML.

    The page embeds each search result as a JSON object inside a <script> tag.
    """
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    articles: list = []
    seen_urls: set[str] = set()
    for s in scripts:
        if len(s) < 1000:
            continue
        if not s.strip().startswith("{"):
            continue
        try:
            data = json.loads(s).get("data", {})
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue

        title = data.get("title", "")
        tpl = data.get("template_key", "")
        if not title:
            continue
        if any(tpl.startswith(p) for p in _SKIP_TEMPLATES):
            continue

        # article_url is the primary field; display paths are fallbacks
        article_url = (
            data.get("article_url", "")
            or data.get("source_url", "")
            or (data.get("display") or {}).get("info", {}).get("url", "")
        )

        if not article_url or article_url in seen_urls:
            continue
        seen_urls.add(article_url)

        articles.append({
            "title": title,
            "url": article_url,
            "source": data.get("media_name", "") or data.get("source", ""),
            "abstract": (data.get("abstract", "") or "")[:300],
            "publish_time": data.get("publish_time"),
            "read_count": data.get("read_count"),
            "comment_count": data.get("comment_count"),
        })
    return articles


class ToutiaoChannel(Channel):
    name = "toutiao"
    description = "今日头条搜索与资讯"
    backends = ["Toutiao Web (public)"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "toutiao.com" in d

    def check(self, config=None) -> Tuple[str, str]:
        try:
            test_url = _SEARCH_URL.format(keyword="test")
            content = _request_body(
                test_url,
                headers={"User-Agent": _UA},
                timeout=_TIMEOUT_SEARCH,
                attempts=_SEARCH_ATTEMPTS,
            ).decode("utf-8", errors="replace")
            if "data" in content or "title" in content:
                return "ok", "头条搜索可用（搜索文章、视频、资讯；依赖页面内嵌 JSON，可能随站点改版变化）"
            return "warn", "头条搜索返回非预期内容"
        except Exception as e:
            return "warn", f"头条搜索连接失败（可稍后重试或检查网络/代理）：{e}"

    def read(self, url: str) -> str:
        """通过 Jina Reader 读取头条文章正文。"""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        jina_url = f"https://r.jina.ai/{url}"
        data = _request_body(
            jina_url,
            headers={"User-Agent": _UA, "Accept": "text/plain"},
            timeout=_TIMEOUT_READ,
            attempts=_READ_ATTEMPTS,
        )
        return data.decode("utf-8", errors="replace")

    def search(self, keyword: str, limit: int = 10) -> list:
        """搜索头条文章。

        Args:
            keyword: 搜索关键词
            limit:   最多返回条数

        Returns:
            list of dicts with keys:
              title, url, source, abstract, publish_time, read_count, comment_count
        """
        encoded = urllib.parse.quote(keyword)
        url = _SEARCH_URL.format(keyword=encoded)
        html = _fetch_html(url)
        return _parse_search_results(html)[:limit]

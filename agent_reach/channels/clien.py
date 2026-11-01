# -*- coding: utf-8 -*-
"""Clien — read-only channel for the Korean community clien.net.

Server-rendered classic board pages, so search and read work over plain HTTP.
Experimental: markup can change and break extraction.
"""

import re
from html.parser import HTMLParser
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen

from agent_reach.runtime.result import BAD_INPUT, NOT_FOUND, UPSTREAM_BROKEN, ReachError, make_item
from agent_reach.utils.htmltext import extract_text, extract_title

from .base import Action, Channel, Param

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_TIMEOUT = 12
_MAX_BYTES = 3 * 1024 * 1024
_MIN_TEXT_CHARS = 80
_BASE = "https://www.clien.net"
_HOSTS = ("clien.net", "www.clien.net")

_POST_URL_RE = re.compile(r"^https://(?:www\.)?clien\.net/service/board/\w+/\d+")


def _article_text(html: str) -> str:
    """Prefer the post body container; fall back to whole-page text.

    Clien renders the article inside <div class="post_content">... and comments
    after it, so slicing that block drops the nav chrome and the comment list.
    """
    match = re.search(r'class="post_content"', html)
    if match:
        start = match.start()
        end = html.find("comment", start)
        if end == -1 or end <= start:
            end = min(start + 200_000, len(html))
        text = extract_text(html[start:end])
        if len(text) >= _MIN_TEXT_CHARS:
            return text
    return extract_text(html)


def _fetch(url: str) -> str:
    """Fetch a clien page as text; urllib is enough (no bot wall on boards)."""
    req = Request(url, headers={"User-Agent": _UA, "Accept-Language": "ko"})
    with urlopen(req, timeout=_TIMEOUT) as resp:
        body = resp.read(_MAX_BYTES + 1)
    if len(body) > _MAX_BYTES:
        raise ReachError(UPSTREAM_BROKEN, "clien response exceeds the 3 MiB safety limit")
    return body.decode("utf-8", errors="replace")


class _LinkParser(HTMLParser):
    """Collect board post links and their anchor text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._text).strip()))
            self._href = None


class ClienChannel(Channel):
    name = "clien"
    description = "클리앙(clien.net) 검색과 글 읽기 (experimental)"

    level = "experimental"
    actions = (
        Action(
            "search",
            "Search clien.net posts (titles and links; use read for full text)",
            (
                Param("query", "search keyword"),
                Param("limit", "max items", required=False, type=int, default=10),
            ),
            (("site-html", "_html_search"),),
            public_web=_HOSTS,
        ),
        Action(
            "read",
            "Read a clien.net post and its comments",
            (Param("target", "clien.net post URL"),),
            (("site-html", "_html_read"),),
            public_web=_HOSTS,
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "clien.net")

    # ------------------------------------------------------------------ #
    # Backends
    # ------------------------------------------------------------------ #

    def _html_search(self, *, query: str, limit: int, timeout: float) -> list:
        html = _fetch(f"{_BASE}/service/search?q={quote_plus(query)}")
        parser = _LinkParser()
        try:
            parser.feed(html)
        except Exception as exc:
            raise ReachError(UPSTREAM_BROKEN, f"could not parse clien search page: {exc}") from exc
        seen: set[str] = set()
        items = []
        for href, text in parser.links:
            url = urljoin(_BASE, href)
            if not _POST_URL_RE.match(url) or not text:
                continue
            canonical = url.split("#", 1)[0].split("?", 1)[0]
            if canonical in seen:
                continue
            seen.add(canonical)
            items.append(make_item(title=text, url=canonical, text=None, raw={"source": "site-html"}))
            if len(items) >= limit:
                break
        if not items:
            raise ReachError(NOT_FOUND, f"no clien posts found for: {query}")
        return items

    def _html_read(self, *, target: str, timeout: float) -> list:
        url = str(target).strip()
        if "://" not in url:
            url = "https://" + url
        if not _POST_URL_RE.match(url):
            raise ReachError(BAD_INPUT, "target must be a clien.net post URL (https://www.clien.net/service/board/<board>/<id>)")
        html = _fetch(url)
        title = extract_title(html)
        text = _article_text(html)
        if len(text) < _MIN_TEXT_CHARS:
            raise ReachError(UPSTREAM_BROKEN, "clien page came back without readable text", hint="Retry with --backend public-web.")
        return [make_item(title=title, url=url, text=text, raw={"source": "site-html"})]

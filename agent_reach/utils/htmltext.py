# -*- coding: utf-8 -*-
"""Best-effort HTML → title/plain-text extraction for server-rendered pages.

Used by the experimental Korean community channels (naver, clien, fmkorea).
These sites have no public JSON API, so channels fetch the HTML page and pull
out readable text. Extraction is conservative: scripts, styles and hidden
blocks are dropped; callers must treat short output as "not enough content".
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "iframe", "head"}
_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "section", "article", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "td", "pre"}


class _TextParser(HTMLParser):
    """Collect visible text; convert element boundaries to newlines."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._block_pending = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._block_pending = True

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not data:
            return
        if self._block_pending and self._chunks and not self._chunks[-1].endswith("\n"):
            self._chunks.append("\n")
            self._block_pending = False
        self._chunks.append(data)


class _TitleParser(HTMLParser):
    """Collect the contents of <title> (or og:title as a fallback)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.og_title: str | None = None
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            attr = {k.lower(): v for k, v in attrs}
            if attr.get("property") == "og:title":
                self.og_title = attr.get("content")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and self.title is None:
            self.title = data


def extract_title(html: str) -> str | None:
    """Return the page <title> (og:title preferred when it reads better)."""
    parser = _TitleParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    for candidate in (parser.og_title, parser.title):
        if candidate and candidate.strip():
            text = _squash(candidate)
            # Portal titles carry suffixes (" : 네이버 블로그"); trim one trailing segment.
            return re.sub(r"\s*[\|:-]\s*[^|:-]{1,20}$", "", text).strip() or text
    return None


def extract_text(html: str) -> str:
    """Return visible page text with line breaks preserved per block element."""
    parser = _TextParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    lines = [_squash(line) for line in "".join(parser._chunks).splitlines()]
    return "\n".join(line for line in lines if line)


def _squash(text: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()

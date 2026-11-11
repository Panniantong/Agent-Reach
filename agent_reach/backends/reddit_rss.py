# -*- coding: utf-8 -*-
"""Reddit's public Atom feeds, used when the browser path gets HTML instead of JSON.

Reddit answers its `.json` endpoints with a "blocked by network security" page
on some networks, even for a logged-in browser, while the `.rss` feeds of the
same listings stay available without login. The feeds are rate limited per IP
(about one request per half minute), so a short limit is waited out once and a
longer one is reported as a transient failure: a channel-wide RATE_LIMITED
would pause every Reddit action for an hour over a 30-second feed limit.
"""

from __future__ import annotations

import datetime as _dt
import html
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import List, Optional

from agent_reach import __version__
from agent_reach.runtime.result import BAD_INPUT, NOT_FOUND, UPSTREAM_BROKEN, ReachError, make_item

BACKEND = "rss"
_BASE = "https://www.reddit.com"
_UA = f"agent-reach/{__version__}"
_MAX_BYTES = 2 * 1024 * 1024
_MAX_WAIT_SECONDS = 35
_ATOM = "{http://www.w3.org/2005/Atom}"
_SUBREDDIT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]{1,20}$")
_FOOTER_RE = re.compile(r"\s*submitted by\s+/u/\S+\s*(\[link\])?\s*(\[comments\])?\s*$")
_BLOCK_TAGS = {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "table"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(value: Optional[str]) -> str:
    """Plain text of a feed entry's HTML body, without Reddit's 'submitted by' footer."""
    if not value:
        return ""
    parser = _Text()
    parser.feed(value)
    parser.close()
    text = "".join(parser.parts)
    text = "\n".join(re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return _FOOTER_RE.sub("", text).strip()


def _iso(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _reset_seconds(headers) -> Optional[int]:
    for name in ("x-ratelimit-reset", "retry-after"):
        raw = headers.get(name) if headers is not None else None
        if raw is None:
            continue
        try:
            return max(1, int(float(raw)))
        except (TypeError, ValueError):
            continue
    return None


def _open(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/atom+xml"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(_MAX_BYTES + 1)
        ctype = resp.headers.get("Content-Type", "")
    if len(raw) > _MAX_BYTES:
        raise ReachError(UPSTREAM_BROKEN, "Reddit RSS response exceeds the 2 MiB safety limit")
    if "xml" not in ctype.lower():
        raise ReachError(UPSTREAM_BROKEN, "Reddit returned a web page instead of an RSS feed")
    return raw


def fetch(path: str, timeout: float) -> bytes:
    """GET a reddit.com feed path, waiting out one short rate limit when the time budget allows."""
    deadline = time.monotonic() + timeout
    url = _BASE + path
    for attempt in range(2):
        left = deadline - time.monotonic()
        if left <= 1:
            break
        try:
            return _open(url, min(left, 20.0))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = _reset_seconds(exc.headers) or 30
                if attempt == 0 and wait <= _MAX_WAIT_SECONDS and deadline - time.monotonic() > wait + 3:
                    time.sleep(wait + 1)
                    continue
                raise ReachError(
                    UPSTREAM_BROKEN, f"Reddit RSS feed is rate limited for about {wait} seconds",
                    hint=f"Reddit's public feeds allow about one request per {wait} seconds from this network; "
                         "retry after that. Do not loop.",
                ) from None
            if exc.code == 404:
                raise ReachError(NOT_FOUND, "Reddit has no such subreddit or post") from None
            body = b""
            try:
                body = exc.read(4096)
            except Exception:  # noqa: BLE001 - the body only refines the message
                pass
            if b"blocked by network security" in body:
                raise ReachError(UPSTREAM_BROKEN, "Reddit blocked this network for RSS too (HTTP 403)") from None
            raise ReachError(UPSTREAM_BROKEN, f"Reddit RSS HTTP {exc.code}") from None
    raise ReachError(UPSTREAM_BROKEN, "Reddit RSS feed stayed rate limited",
                     hint="Retry this Reddit action in about a minute. Do not loop.")


def parse_feed(raw: bytes) -> List[dict]:
    """Atom feed bytes → normalized items (no DTDs or entities accepted)."""
    head = raw[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise ReachError(UPSTREAM_BROKEN, "Reddit RSS feed contains a DTD; refusing to parse it")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise ReachError(UPSTREAM_BROKEN, "Reddit returned an RSS feed that is not valid XML") from None
    items = []
    for entry in root.findall(f"{_ATOM}entry"):
        link = entry.find(f"{_ATOM}link")
        category = entry.find(f"{_ATOM}category")
        author = (entry.findtext(f"{_ATOM}author/{_ATOM}name") or "").strip()
        items.append(make_item(
            title=html.unescape((entry.findtext(f"{_ATOM}title") or "").strip()),
            url=link.get("href") if link is not None else None,
            author=author.removeprefix("/u/") or None,
            published_at=_iso(entry.findtext(f"{_ATOM}published") or entry.findtext(f"{_ATOM}updated")),
            text=html_to_text(entry.findtext(f"{_ATOM}content")),
            raw={"id": (entry.findtext(f"{_ATOM}id") or "").strip() or None,
                 "subreddit": category.get("label") if category is not None else None,
                 "source": "reddit-rss"},
        ))
    return items


def subreddit(name: str, limit: int, timeout: float) -> List[dict]:
    """Newest posts of a public subreddit."""
    sub = str(name).strip().removeprefix("/").removeprefix("r/")
    if not _SUBREDDIT_RE.match(sub):
        raise ReachError(BAD_INPUT, "name must be a subreddit name such as python (letters, digits, underscore)")
    limit = max(1, min(int(limit), 100))
    items = parse_feed(fetch(f"/r/{sub}/new/.rss?limit={limit}", timeout))
    if not items:
        raise ReachError(NOT_FOUND, f"r/{sub} has no public posts in its feed")
    return items[:limit]

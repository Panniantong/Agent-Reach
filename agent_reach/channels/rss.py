# -*- coding: utf-8 -*-
"""RSS — feedparser availability check + root-URL feed discovery."""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from agent_reach.utils.text import scrub_url_credentials
from agent_reach.utils.url import normalize_public_http_url

from .base import Channel

_UA = "agent-reach/1.0"
_TIMEOUT = 10
_MAX_RESPONSE_BYTES = 1024 * 1024
_LOG = logging.getLogger(__name__)

# Common self-hosted / CMS feed paths (issue #322). Kept short so discovery
# stays bounded for agents that pass an arbitrary site root.
_COMMON_FEED_PATHS = (
    "/feed",
    "/rss",
    "/atom.xml",
    "/feed.xml",
    "/rss.xml",
    "/index.xml",
    "/atom",
    "/.well-known/feed",
)

_FEED_LINK_TYPES = {
    "application/rss+xml",
    "application/atom+xml",
    "application/feed+json",
    "application/json",
    "text/xml",
    "application/xml",
}


class _AlternateFeedLinkParser(HTMLParser):
    """Collect ``<link rel=\"alternate\" type=… href=…>`` feed candidates."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, str]] = []  # href, type, title

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "link":
            return
        mapping = {k.lower(): (v or "") for k, v in attrs if k}
        rel = mapping.get("rel", "").lower()
        if "alternate" not in rel.split():
            return
        href = mapping.get("href", "").strip()
        if not href:
            return
        typ = mapping.get("type", "").split(";", 1)[0].strip().lower()
        title = mapping.get("title", "").strip()
        # Prefer typed feed links; still keep untyped alternate that looks like a feed path.
        if typ and typ not in _FEED_LINK_TYPES and "rss" not in typ and "atom" not in typ and "json" not in typ:
            return
        if not typ:
            low = href.lower()
            if not any(x in low for x in ("/feed", "/rss", "atom", ".xml", "json")):
                return
        self.links.append((href, typ, title))


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _canonical_feed_key(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), (parts.netloc or "").lower(), path, "", ""))


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "text/html,*/*"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        raw = resp.read(_MAX_RESPONSE_BYTES + 1)
        charset = resp.headers.get_content_charset() or "utf-8"
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError("response exceeds the 1 MiB safety limit")
    return raw.decode(charset, errors="replace")


def _looks_like_feed(parsed: Any) -> bool:
    version = getattr(parsed, "version", None) or ""
    entries = list(getattr(parsed, "entries", None) or [])
    feed = getattr(parsed, "feed", None)
    has_feed_meta = False
    if feed is not None:
        title = getattr(feed, "title", None) or (feed.get("title") if isinstance(feed, dict) else None)
        link = getattr(feed, "link", None) or (feed.get("link") if isinstance(feed, dict) else None)
        has_feed_meta = bool(title or link)
    return bool(version) or bool(entries) or has_feed_meta


def _validate_feed(url: str) -> dict[str, str] | None:
    """Return a feed record if ``url`` parses as RSS/Atom/JSON Feed, else None."""
    import feedparser

    try:
        parsed = feedparser.parse(url)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("feed parse raised for %s: %s", scrub_url_credentials(url), scrub_url_credentials(exc))
        return None
    if not _looks_like_feed(parsed):
        bozo = getattr(parsed, "bozo_exception", None)
        detail = scrub_url_credentials(bozo) if bozo else "not a feed"
        _LOG.info("rejecting candidate %s (%s)", scrub_url_credentials(url), detail)
        return None
    feed = getattr(parsed, "feed", None)
    title = ""
    if feed is not None:
        title = str(
            getattr(feed, "title", None)
            or (feed.get("title") if isinstance(feed, dict) else "")
            or ""
        )
    version = str(getattr(parsed, "version", None) or "")
    feed_type = "rss"
    low = version.lower()
    if "atom" in low:
        feed_type = "atom"
    elif "json" in low:
        feed_type = "json"
    return {
        "url": url,
        "title": title,
        "type": feed_type,
        "version": version,
    }


def discover_feeds(root_url: str) -> list[dict[str, str]]:
    """Discover RSS/Atom/JSON feeds reachable from a site root URL.

    Strategy (issue #322 MVP):
    1. Normalize ``root_url`` with the public-HTTP gate.
    2. Parse ``<link rel="alternate" …>`` tags from the homepage HTML.
    3. Probe a small set of common feed paths under the same origin.
    4. Validate each candidate with feedparser; drop failures (logged).
    5. Deduplicate by canonical URL.

    Out of scope for this MVP: robots.txt, external registries, and
    scheduled re-scans (callers can re-invoke on their own schedule).
    """
    root = normalize_public_http_url(root_url)
    origin = _origin(root)
    candidates: list[tuple[str, str]] = []  # url, source
    seen_keys: set[str] = set()

    def _add_candidate(raw_href: str, source: str) -> None:
        abs_url = urljoin(root if root.endswith("/") else root + "/", raw_href)
        try:
            normalized = normalize_public_http_url(abs_url)
        except ValueError as exc:
            _LOG.info(
                "skipping unsafe candidate from %s (%s): %s",
                source,
                scrub_url_credentials(raw_href),
                scrub_url_credentials(exc),
            )
            return
        # Stay on the same host — discovery is for one site root, not open redirects.
        if urlsplit(normalized).netloc.lower() != urlsplit(origin).netloc.lower():
            _LOG.info(
                "skipping off-host candidate %s (from %s)",
                scrub_url_credentials(normalized),
                source,
            )
            return
        key = _canonical_feed_key(normalized)
        if key in seen_keys:
            return
        seen_keys.add(key)
        candidates.append((normalized, source))

    try:
        html = _fetch_text(root)
        parser = _AlternateFeedLinkParser()
        parser.feed(html)
        for href, typ, _title in parser.links:
            _add_candidate(href, f"html-link:{typ or 'untyped'}")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        _LOG.warning(
            "homepage fetch failed for %s: %s",
            scrub_url_credentials(root),
            scrub_url_credentials(exc),
        )

    for path in _COMMON_FEED_PATHS:
        _add_candidate(urljoin(origin + "/", path.lstrip("/")), f"common-path:{path}")

    results: list[dict[str, str]] = []
    result_keys: set[str] = set()
    for url, source in candidates:
        record = _validate_feed(url)
        if record is None:
            _LOG.info("discovery miss (%s): %s", source, scrub_url_credentials(url))
            continue
        key = _canonical_feed_key(record["url"])
        if key in result_keys:
            continue
        result_keys.add(key)
        record["source"] = source
        results.append(record)
    return results


class RSSChannel(Channel):
    name = "rss"
    description = "RSS/Atom 订阅源"
    backends = ["feedparser"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return any(x in url.lower() for x in ["/feed", "/rss", ".xml", "atom"])

    def check(self, config=None):
        try:
            import feedparser  # noqa: F401
        except ImportError:
            self.active_backend = None
            return "off", "feedparser 未安装。安装：pip install feedparser"
        except Exception as e:
            # 已安装但导入期崩溃（半残安装/版本冲突）→ 重装处方
            self.active_backend = None
            return "error", f"feedparser 导入失败：{e}\n修复：pip install --force-reinstall feedparser"
        self.active_backend = self.backends[0]
        return "ok", "可读取 RSS/Atom 源"

    def discover_feeds(self, root_url: str) -> list[dict[str, str]]:
        """See module-level :func:`discover_feeds`."""
        return discover_feeds(root_url)

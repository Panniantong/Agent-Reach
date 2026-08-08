# -*- coding: utf-8 -*-
"""Substack — public RSS + JSON API for publication posts."""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any
from urllib.parse import quote, urlsplit

from agent_reach.utils.text import scrub_url_credentials
from agent_reach.utils.url import host_matches

from .base import Channel

_UA = "agent-reach/1.0"
_TIMEOUT = 10
_MAX_RESPONSE_BYTES = 1024 * 1024
_SLUG_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
_PROBE_PUBLICATION = "platformer"


def _parse_publication(url_or_slug: str) -> str:
    """Return a Substack publication slug from a URL or bare slug.

    Accepts ``lenny``, ``lenny.substack.com``, or
    ``https://lenny.substack.com/p/...``. Custom domains are intentionally
    rejected so they keep falling through to the generic web channel.
    """
    raw = str(url_or_slug or "").strip()
    if not raw:
        raise ValueError("empty Substack publication")

    if "://" not in raw and "/" not in raw and "." not in raw:
        if not _SLUG_RE.fullmatch(raw):
            raise ValueError("invalid Substack publication slug")
        return raw.lower()

    candidate = raw if "://" in raw else f"https://{raw}"
    try:
        parsed = urlsplit(candidate)
        host = (parsed.hostname or "").lower().rstrip(".")
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("invalid Substack URL") from exc

    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("invalid Substack URL")

    if host.endswith(".substack.com"):
        pub = host[: -len(".substack.com")]
        if pub and "." not in pub and pub != "www" and _SLUG_RE.fullmatch(pub):
            return pub.lower()
    raise ValueError("only *.substack.com publication hosts are supported")


def _feed_url(publication: str) -> str:
    pub = _parse_publication(publication)
    return f"https://{pub}.substack.com/feed"


def _api_post_url(publication: str, slug: str) -> str:
    pub = _parse_publication(publication)
    post_slug = str(slug or "").strip().strip("/")
    # Post slugs commonly include underscores; keep them path-safe.
    if not post_slug or "/" in post_slug or not re.fullmatch(
        r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,200}", post_slug
    ):
        raise ValueError("invalid Substack post slug")
    return f"https://{pub}.substack.com/api/v1/posts/{quote(post_slug, safe='')}"


def _validate_substack_https_url(url: str, *, allow_feed: bool = False) -> None:
    """Allow only HTTPS URLs on ``*.substack.com`` (no userinfo / odd ports)."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid Substack URL") from exc
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme.lower() != "https"
        or not host.endswith(".substack.com")
        or host.count(".") < 2
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("only Substack HTTPS publication URLs are allowed")
    path = parsed.path or "/"
    if allow_feed:
        if path not in {"/feed", "/feed/"}:
            raise ValueError("only Substack feed URLs are allowed")
    elif not path.startswith("/api/v1/posts/"):
        raise ValueError("only Substack post API URLs are allowed")


def _get_json(url: str) -> Any:
    _validate_substack_https_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        raw = resp.read(_MAX_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError("Substack API response exceeds the 1 MiB safety limit")
    return json.loads(raw.decode("utf-8"))


def _entry_field(entry: Any, *names: str) -> str:
    for name in names:
        value = getattr(entry, name, None)
        if value:
            return str(value)
        if isinstance(entry, dict) and entry.get(name):
            return str(entry[name])
    return ""


class SubstackChannel(Channel):
    name = "substack"
    description = "Substack Newsletter 与文章"
    backends = ["Substack RSS (feedparser)"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "substack.com")

    def check(self, config=None):
        try:
            import feedparser
        except ImportError:
            self.active_backend = None
            return "off", "feedparser 未安装。安装：pip install feedparser"
        except Exception as e:
            self.active_backend = None
            return (
                "error",
                f"feedparser 导入失败：{e}\n修复：pip install --force-reinstall feedparser",
            )

        try:
            parsed = feedparser.parse(_feed_url(_PROBE_PUBLICATION))
            entries = list(getattr(parsed, "entries", None) or [])
            if not entries:
                bozo = getattr(parsed, "bozo_exception", None)
                detail = scrub_url_credentials(bozo) if bozo else "empty feed"
                raise RuntimeError(detail)
            self.active_backend = self.backends[0]
            return "ok", "公开 RSS 可用（出版物列表与文章读取）"
        except Exception as e:
            self.active_backend = None
            return (
                "warn",
                f"Substack RSS 连接失败（可能需要代理）：{scrub_url_credentials(e)}",
            )

    def list_posts(self, publication: str, limit: int = 10) -> list:
        """List recent posts for a Substack publication via its public feed.

        Returns dicts with keys: title, url, published, summary, author.
        """
        import feedparser

        limit = max(1, min(int(limit), 50))
        feed_url = _feed_url(publication)
        _validate_substack_https_url(feed_url, allow_feed=True)
        parsed = feedparser.parse(feed_url)
        results = []
        for entry in list(getattr(parsed, "entries", None) or [])[:limit]:
            results.append(
                {
                    "title": _entry_field(entry, "title"),
                    "url": _entry_field(entry, "link"),
                    "published": _entry_field(entry, "published", "updated"),
                    "summary": _entry_field(entry, "summary", "description"),
                    "author": _entry_field(entry, "author"),
                }
            )
        return results

    def get_post(self, publication: str, slug: str) -> dict:
        """Fetch one post via Substack's public JSON API.

        Returns title, url, published, audience, and body_html (may be empty
        or truncated for paywalled posts — this does not bypass paywalls).
        """
        data = _get_json(_api_post_url(publication, slug))
        if not isinstance(data, dict):
            raise ValueError("unexpected Substack post payload")
        pub = _parse_publication(publication)
        post_slug = str(slug or "").strip().strip("/")
        return {
            "title": str(data.get("title") or ""),
            "url": str(data.get("canonical_url") or f"https://{pub}.substack.com/p/{post_slug}"),
            "published": str(data.get("post_date") or data.get("publishedBylines") or ""),
            "audience": str(data.get("audience") or ""),
            "body_html": str(data.get("body_html") or ""),
            "subtitle": str(data.get("subtitle") or ""),
        }

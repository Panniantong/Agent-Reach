# -*- coding: utf-8 -*-
"""Tests for RSS root-URL feed discovery (#322)."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

from agent_reach.channels import rss as rss_mod
from agent_reach.channels.rss import RSSChannel, discover_feeds


class _FakeHTTPResponse:
    def __init__(self, body: bytes, *, charset: str = "utf-8"):
        self._body = body
        self.headers = SimpleNamespace(get_content_charset=lambda: charset)

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            return self._body
        return self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _install_fake_feedparser(monkeypatch, *, valid_urls: set[str] | None = None):
    valid = valid_urls or set()
    mod = types.ModuleType("feedparser")

    def parse(url: str):
        if url in valid:
            return SimpleNamespace(
                version="rss20",
                entries=[SimpleNamespace(title="t", link=url)],
                feed=SimpleNamespace(title="Example Feed", link=url),
                bozo_exception=None,
            )
        return SimpleNamespace(
            version="",
            entries=[],
            feed=SimpleNamespace(title="", link=""),
            bozo_exception=RuntimeError("not a feed"),
        )

    mod.parse = parse
    monkeypatch.setitem(sys.modules, "feedparser", mod)
    return mod


def test_discover_from_html_alternate_links(monkeypatch):
    html = b"""<!doctype html><html><head>
    <link rel="stylesheet" href="/style.css">
    <link rel="alternate" type="application/rss+xml" title="Blog" href="/blog/rss.xml">
    <link rel="alternate" type="application/atom+xml" href="https://example.com/atom.xml">
    </head><body>hi</body></html>"""
    valid = {
        "https://example.com/blog/rss.xml",
        "https://example.com/atom.xml",
    }
    _install_fake_feedparser(monkeypatch, valid_urls=valid)

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url.rstrip("/") == "https://example.com":
            return _FakeHTTPResponse(html)
        raise AssertionError(f"unexpected fetch {url}")

    with patch.object(rss_mod.urllib.request, "urlopen", side_effect=fake_urlopen):
        found = discover_feeds("https://example.com")

    urls = {f["url"] for f in found}
    assert "https://example.com/blog/rss.xml" in urls
    assert "https://example.com/atom.xml" in urls
    assert all("source" in f for f in found)


def test_discover_common_paths_and_dedupe(monkeypatch):
    html = b"""<!doctype html><html><head>
    <link rel="alternate" type="application/rss+xml" href="/feed">
    </head></html>"""
    valid = {"https://news.example.org/feed"}
    _install_fake_feedparser(monkeypatch, valid_urls=valid)

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        return _FakeHTTPResponse(html)

    with patch.object(rss_mod.urllib.request, "urlopen", side_effect=fake_urlopen):
        found = discover_feeds("https://news.example.org/")

    assert len(found) == 1
    assert found[0]["url"] == "https://news.example.org/feed"
    assert found[0]["type"] == "rss"


def test_discover_rejects_private_and_off_host(monkeypatch):
    html = b"""<!doctype html><html><head>
    <link rel="alternate" type="application/rss+xml" href="http://127.0.0.1/feed">
    <link rel="alternate" type="application/rss+xml" href="https://evil.example/feed">
    </head></html>"""
    _install_fake_feedparser(monkeypatch, valid_urls=set())

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        return _FakeHTTPResponse(html)

    with patch.object(rss_mod.urllib.request, "urlopen", side_effect=fake_urlopen):
        found = discover_feeds("https://example.com")
    assert found == []


def test_discover_rejects_non_public_root():
    try:
        discover_feeds("http://localhost/blog")
    except ValueError:
        return
    raise AssertionError("expected ValueError for localhost root")


def test_channel_method_delegates(monkeypatch):
    _install_fake_feedparser(monkeypatch, valid_urls={"https://example.com/rss.xml"})
    html = b'<link rel="alternate" type="application/rss+xml" href="/rss.xml">'

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        return _FakeHTTPResponse(html)

    with patch.object(rss_mod.urllib.request, "urlopen", side_effect=fake_urlopen):
        found = RSSChannel().discover_feeds("example.com")
    assert found[0]["url"] == "https://example.com/rss.xml"


def test_existing_check_still_ok(monkeypatch):
    monkeypatch.setitem(sys.modules, "feedparser", types.ModuleType("feedparser"))
    status, message = RSSChannel().check()
    assert status == "ok"
    assert "RSS" in message

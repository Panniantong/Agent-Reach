# -*- coding: utf-8 -*-
"""Dedicated tests for the ``substack`` channel."""

import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent_reach.channels import substack as ss
from agent_reach.channels.substack import SubstackChannel


def _install_fake_feedparser(monkeypatch, *, entries=None, bozo_exception=None):
    mod = types.ModuleType("feedparser")

    def parse(_url):
        return SimpleNamespace(
            entries=list(entries or []),
            bozo_exception=bozo_exception,
        )

    mod.parse = parse
    monkeypatch.setitem(sys.modules, "feedparser", mod)
    return mod


def test_can_handle_matches_substack_hosts():
    ch = SubstackChannel()
    for url in [
        "https://lenny.substack.com/p/hello",
        "https://www.substack.com/@someone",
        "https://SUBSTACK.COM/",
    ]:
        assert ch.can_handle(url) is True, url
    for url in [
        "https://substack.com.evil.test/p/x",
        "https://user:pass@lenny.substack.com/p/x",
        "https://example.com",
        "",
    ]:
        assert ch.can_handle(url) is False, url


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("lenny", "lenny"),
        ("Lenny", "lenny"),
        ("lenny.substack.com", "lenny"),
        ("https://lenny.substack.com/p/foo", "lenny"),
        ("https://lenny.substack.com/", "lenny"),
    ],
)
def test_parse_publication_accepts_slug_and_host(raw, expected):
    assert ss._parse_publication(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "www.substack.com",
        "https://substack.com/",
        "https://evil.com",
        "https://user:pass@lenny.substack.com/",
        "not a slug!!",
    ],
)
def test_parse_publication_rejects_garbage(raw):
    with pytest.raises(ValueError):
        ss._parse_publication(raw)


def test_check_ok_sets_active_backend(monkeypatch):
    _install_fake_feedparser(
        monkeypatch,
        entries=[SimpleNamespace(title="t", link="https://platformer.substack.com/p/x")],
    )
    ch = SubstackChannel()
    status, message = ch.check()
    assert status == "ok"
    assert "RSS" in message
    assert ch.active_backend == ch.backends[0]


def test_check_off_when_feedparser_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "feedparser", None)
    ch = SubstackChannel()
    ch.active_backend = "stale"
    status, message = ch.check()
    assert status == "off"
    assert "pip install feedparser" in message
    assert ch.active_backend is None


def test_check_warn_on_empty_feed_clears_backend(monkeypatch):
    _install_fake_feedparser(
        monkeypatch, entries=[], bozo_exception=RuntimeError("boom")
    )
    ch = SubstackChannel()
    ch.active_backend = "stale"
    status, message = ch.check()
    assert status == "warn"
    assert "连接失败" in message
    assert ch.active_backend is None


def test_list_posts_maps_entries_and_respects_limit(monkeypatch):
    entries = [
        SimpleNamespace(
            title=f"T{i}",
            link=f"https://lenny.substack.com/p/{i}",
            published=f"2026-01-0{i}",
            summary=f"S{i}",
            author="A",
        )
        for i in range(1, 6)
    ]
    _install_fake_feedparser(monkeypatch, entries=entries)
    ch = SubstackChannel()
    posts = ch.list_posts("lenny", limit=3)
    assert len(posts) == 3
    assert posts[0]["title"] == "T1"
    assert posts[0]["url"].endswith("/p/1")
    assert posts[0]["summary"] == "S1"


def test_get_post_shapes_api_payload():
    ch = SubstackChannel()
    payload = {
        "title": "Hello",
        "canonical_url": "https://lenny.substack.com/p/hello",
        "post_date": "2026-01-02T00:00:00.000Z",
        "audience": "everyone",
        "body_html": "<p>hi</p>",
        "subtitle": "sub",
    }
    with patch.object(ss, "_get_json", return_value=payload) as get_json:
        post = ch.get_post("lenny", "hello")
    assert post["title"] == "Hello"
    assert post["body_html"] == "<p>hi</p>"
    assert post["audience"] == "everyone"
    get_json.assert_called_once()


@pytest.mark.parametrize(
    "url",
    [
        "http://lenny.substack.com/api/v1/posts/x",
        "https://lenny.substack.com.evil.test/api/v1/posts/x",
        "https://user:pass@lenny.substack.com/api/v1/posts/x",
        "https://lenny.substack.com:8443/api/v1/posts/x",
        "https://lenny.substack.com/p/x",
    ],
)
def test_get_json_rejects_non_api_targets_before_network(url):
    with patch.object(ss.urllib.request, "urlopen") as urlopen:
        with pytest.raises(ValueError, match="Substack"):
            ss._get_json(url)
    urlopen.assert_not_called()

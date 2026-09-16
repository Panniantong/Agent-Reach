# -*- coding: utf-8 -*-
"""Dedicated tests for the ``hackernews`` channel.

Hacker News rides two public APIs: the official Firebase API (story lists,
user profiles, the maxitem health probe) and Algolia's HN Search API (item
detail with a one-shot nested comment tree, full-text search). These tests
stub the shared ``_get_json`` so the shaping logic runs offline, plus
guard the URL allowlist and the response-size cap before any network hop.
Follows the dedicated-channel coverage pattern of v2ex (#331).
"""

from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from agent_reach.channels import hackernews as hn
from agent_reach.channels.hackernews import HackerNewsChannel

# --- can_handle ---


def test_can_handle_matches_hacker_news_hosts():
    ch = HackerNewsChannel()
    for url in [
        "https://news.ycombinator.com/item?id=1",
        "https://NEWS.YCOMBINATOR.COM/item?id=1",
    ]:
        assert ch.can_handle(url) is True, url
    for url in [
        "https://example.com",
        "https://v2ex.com/t/1",
        "https://news.ycombinator.com.evil.test/item?id=1",
        "https://news.ycombinator.com@evil.test/item?id=1",
        "https://user:pass@news.ycombinator.com/item?id=1",
        "",
    ]:
        assert ch.can_handle(url) is False, url


# --- check() ---


def test_check_ok_sets_active_backend():
    ch = HackerNewsChannel()
    with patch.object(hn, "_get_json", return_value=123456):
        status, message = ch.check()
    assert status == "ok"
    assert ch.active_backend == ch.backends[0]
    assert "公开 API 可用" in message


def test_check_warn_on_exception_clears_backend():
    ch = HackerNewsChannel()
    ch.active_backend = "stale"
    with patch.object(hn, "_get_json", side_effect=OSError("no proxy")):
        status, message = ch.check()
    assert status == "warn"
    assert "连接失败" in message
    assert ch.active_backend is None


def test_check_probes_the_smallest_firebase_endpoint():
    ch = HackerNewsChannel()
    captured = {}

    def fake_get_json(url):
        captured["url"] = url
        return 1

    with patch.object(hn, "_get_json", side_effect=fake_get_json):
        ch.check()

    assert captured["url"] == "https://hacker-news.firebaseio.com/v0/maxitem.json"


# --- URL allowlist: rejected before any network hop ---


@pytest.mark.parametrize(
    "url",
    [
        "http://hacker-news.firebaseio.com/v0/maxitem.json",
        "https://hacker-news.firebaseio.com.evil.test/v0/maxitem.json",
        "https://user:pass@hacker-news.firebaseio.com/v0/maxitem.json",
        "https://hacker-news.firebaseio.com:8443/v0/maxitem.json",
        "https://hacker-news.firebaseio.com/about",
        "http://hn.algolia.com/api/v1/search",
        "https://hn.algolia.com.evil.test/api/v1/search",
        "https://user:pass@hn.algolia.com/api/v1/search",
        "https://hn.algolia.com:8443/api/v1/search",
        "https://hn.algolia.com/v1/search",
    ],
)
def test_get_json_rejects_non_api_targets_before_network(url):
    with patch.object(hn.urllib.request, "urlopen") as urlopen:
        with pytest.raises(ValueError, match="Hacker News HTTPS APIs"):
            hn._get_json(url)

    urlopen.assert_not_called()


def test_get_json_accepts_both_api_hosts():
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, _size=-1):
                return b"null"

        return FakeResponse()

    with patch.object(hn.urllib.request, "urlopen", fake_urlopen):
        assert hn._get_json("https://hacker-news.firebaseio.com/v0/item/1.json") is None
        assert hn._get_json("https://hn.algolia.com/api/v1/search?query=x") is None

    assert calls == [
        "https://hacker-news.firebaseio.com/v0/item/1.json",
        "https://hn.algolia.com/api/v1/search?query=x",
    ]


def test_get_json_enforces_response_size_cap():
    class BigResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, _size=-1):
            return b"x" * (hn._MAX_RESPONSE_BYTES + 1)

    with patch.object(hn.urllib.request, "urlopen", return_value=BigResponse()):
        with pytest.raises(ValueError, match="1 MiB safety limit"):
            hn._get_json("https://hacker-news.firebaseio.com/v0/maxitem.json")


# --- get_stories ---


def test_get_stories_maps_fields_and_respects_limit():
    ch = HackerNewsChannel()
    ids = [1, 2, 3]
    items = {
        1: {
            "id": 1,
            "title": "Show HN: Agent Reach",
            "score": 120,
            "descendants": 45,
            "by": "pg",
            "time": 1700000000,
            "url": "https://example.com",
            "text": "x" * 300,
        },
        2: {"id": 2, "title": "Ask HN: best CLI?", "score": 5},
        3: {"id": 3, "title": "unreachable"},
    }

    def fake_get_json(url):
        if url.endswith("/topstories.json"):
            return ids
        if "item/3" in url:
            raise OSError("flaky item")
        if "item/2" in url:
            return None  # deleted item → Firebase null
        return items[1]

    with patch.object(hn, "_get_json", side_effect=fake_get_json):
        stories = ch.get_stories("top", limit=3)

    assert len(stories) == 1  # one mapped, one null-skipped, one failed-skipped
    s = stories[0]
    assert s["title"] == "Show HN: Agent Reach"
    assert s["hn_url"] == "https://news.ycombinator.com/item?id=1"
    assert s["score"] == 120
    assert s["comments"] == 45
    assert len(s["text"]) == 200  # preview truncated like V2EX


def test_get_stories_rejects_unknown_kind_without_network():
    ch = HackerNewsChannel()
    with patch.object(hn, "_get_json", side_effect=AssertionError("must not fetch")):
        with pytest.raises(ValueError, match="unknown story kind"):
            ch.get_stories("hot")


def test_get_stories_percent_encodes_item_id_in_path():
    ch = HackerNewsChannel()
    captured = []

    def fake_get_json(url):
        captured.append(url)
        if url.endswith("/topstories.json"):
            return ["1#&evil=1"]
        return {"id": 1, "title": "x"}

    with patch.object(hn, "_get_json", side_effect=fake_get_json):
        ch.get_stories("top", limit=1)

    parts = urlsplit(captured[1])
    assert parts.path == "/v0/item/1%23%26evil%3D1.json"
    assert parts.fragment == ""


# --- get_item: nested comment tree flattened depth-first ---


def test_get_item_flattens_comment_tree_with_depths():
    ch = HackerNewsChannel()
    algolia = {
        "id": 42,
        "title": "Story",
        "url": "https://example.com",
        "author": "op",
        "points": 99,
        "num_comments": 3,
        "created_at": "2026-01-01T00:00:00Z",
        "story_text": "<p>body</p>",
        "children": [
            {
                "id": 100,
                "author": "alice",
                "text": "c1",
                "created_at": "2026-01-01T01:00:00Z",
                "children": [
                    {
                        "id": 101,
                        "author": "bob",
                        "text": "c1-reply",
                        "created_at": "2026-01-01T02:00:00Z",
                        "children": [],
                    }
                ],
            },
            {
                "id": 102,
                "author": "carol",
                "text": "c2",
                "created_at": "2026-01-01T03:00:00Z",
                "children": [],
            },
        ],
    }
    with patch.object(hn, "_get_json", return_value=algolia):
        result = ch.get_item(42)

    assert result["id"] == 42
    assert result["hn_url"] == "https://news.ycombinator.com/item?id=42"
    assert result["points"] == 99
    assert [c["author"] for c in result["comments_tree"]] == ["alice", "bob", "carol"]
    assert [c["depth"] for c in result["comments_tree"]] == [0, 1, 0]
    assert result["comments_tree"][0]["children"] == 1


def test_get_item_uses_algolia_items_endpoint_in_one_request():
    ch = HackerNewsChannel()
    captured = {}

    def fake_get_json(url):
        captured["url"] = url
        return {"id": 42, "children": []}

    with patch.object(hn, "_get_json", side_effect=fake_get_json):
        ch.get_item("42#&evil=1")

    parts = urlsplit(captured["url"])
    assert parts.netloc == "hn.algolia.com"
    assert parts.path == "/api/v1/items/42%23%26evil%3D1"
    assert parts.fragment == ""


def test_get_item_raises_for_missing_item():
    ch = HackerNewsChannel()
    with patch.object(hn, "_get_json", return_value=None):
        with pytest.raises(ValueError, match="not found"):
            ch.get_item(99999999)


# --- get_user ---


def test_get_user_maps_fields():
    ch = HackerNewsChannel()
    data = {
        "id": "dang",
        "karma": 300000,
        "about": "moderator",
        "created": 1160418021,
        "submitted": [1, 2, 3],
    }
    with patch.object(hn, "_get_json", return_value=data):
        user = ch.get_user("dang")
    assert user["username"] == "dang"
    assert user["karma"] == 300000
    assert user["hn_url"] == "https://news.ycombinator.com/user?id=dang"
    assert user["submitted"] == [1, 2, 3]


def test_get_user_percent_encodes_username_in_path():
    ch = HackerNewsChannel()
    captured = {}

    def fake_get_json(url):
        captured["url"] = url
        return {"id": "a b"}

    with patch.object(hn, "_get_json", side_effect=fake_get_json):
        ch.get_user("a b/c")

    assert captured["url"].endswith("/user/a%20b%2Fc.json")


def test_get_user_raises_for_missing_user():
    ch = HackerNewsChannel()
    with patch.object(hn, "_get_json", return_value=None):
        with pytest.raises(ValueError, match="not found"):
            ch.get_user("no-such-user-xyz")


# --- search: Algolia query encoding + hit mapping ---


def test_search_encodes_query_and_maps_hits():
    ch = HackerNewsChannel()
    captured = {}
    payload = {
        "hits": [
            {
                "objectID": "77",
                "title": "Python 3.14 released",
                "url": "https://python.org",
                "author": "guido",
                "points": 500,
                "num_comments": 80,
                "created_at_i": 1700000000,
                "story_text": "<p>release notes</p>",
            },
            {
                "objectID": "78",
                "story_title": "comment parent",
                "story_url": "https://example.com",
                "author": "alice",
                "comment_text": "related comment",
                "created_at_i": 1700000001,
            },
        ]
    }

    def fake_get_json(url):
        captured["url"] = url
        return payload

    with patch.object(hn, "_get_json", side_effect=fake_get_json):
        results = ch.search("python & go#lang", limit=2)

    parts = urlsplit(captured["url"])
    assert parts.netloc == "hn.algolia.com"
    assert parts.fragment == ""
    query = parse_qs(parts.query)
    assert query["query"] == ["python & go#lang"]
    assert query["tags"] == ["story"]
    assert query["hitsPerPage"] == ["2"]

    assert len(results) == 2
    assert results[0]["hn_url"] == "https://news.ycombinator.com/item?id=77"
    assert results[0]["points"] == 500
    assert results[0]["snippet"] == "<p>release notes</p>"
    # comment 命中回退到 story_title/story_url
    assert results[1]["title"] == "comment parent"
    assert results[1]["url"] == "https://example.com"
    assert results[1]["snippet"] == "related comment"


def test_search_without_tags_omits_the_parameter():
    ch = HackerNewsChannel()
    captured = {}

    def fake_get_json(url):
        captured["url"] = url
        return {"hits": []}

    with patch.object(hn, "_get_json", side_effect=fake_get_json):
        assert ch.search("anything", tags="") == []

    assert "tags" not in parse_qs(urlsplit(captured["url"]).query)

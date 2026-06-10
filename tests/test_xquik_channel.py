# -*- coding: utf-8 -*-
"""Tests for XquikChannel — API-key-based X/Twitter channel."""

import json
import urllib.error
import urllib.request

import pytest

from agent_reach.channels.xquik import XquikChannel, _get_json

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture()
def channel():
    return XquikChannel()


# ------------------------------------------------------------------ #
# can_handle
# ------------------------------------------------------------------ #


class TestCanHandle:
    def test_x_dot_com(self, channel):
        assert channel.can_handle("https://x.com/elonmusk/status/123")

    def test_twitter_dot_com(self, channel):
        assert channel.can_handle("https://twitter.com/user/status/456")

    def test_www_x_dot_com(self, channel):
        assert channel.can_handle("https://www.x.com/user")

    def test_mobile_twitter(self, channel):
        assert channel.can_handle("https://mobile.twitter.com/user/status/1")

    def test_rejects_github(self, channel):
        assert not channel.can_handle("https://github.com/user/repo")

    def test_rejects_reddit(self, channel):
        assert not channel.can_handle("https://reddit.com/r/Python")

    def test_rejects_xquik(self, channel):
        assert not channel.can_handle("https://xquik.com/dashboard")


# ------------------------------------------------------------------ #
# check — health diagnostics
# ------------------------------------------------------------------ #


class TestCheck:
    def test_no_api_key(self, channel, monkeypatch):
        monkeypatch.delenv("XQUIK_API_KEY", raising=False)
        status, msg = channel.check()
        assert status == "off"
        assert "XQUIK_API_KEY" in msg

    def test_api_key_valid(self, channel, monkeypatch):
        monkeypatch.setenv("XQUIK_API_KEY", "xk_test_key_123")

        fake_response = json.dumps({"trends": [{"name": "#AI", "rank": 1}]}).encode()

        class FakeResp:
            def read(self):
                return fake_response

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResp())
        status, msg = channel.check()
        assert status == "ok"
        assert "搜索推文" in msg

    def test_api_key_invalid_401(self, channel, monkeypatch):
        monkeypatch.setenv("XQUIK_API_KEY", "xk_bad_key")

        def raise_401(req, timeout=None):
            raise urllib.error.HTTPError(url="", code=401, msg="Unauthorized", hdrs={}, fp=None)

        monkeypatch.setattr(urllib.request, "urlopen", raise_401)
        status, msg = channel.check()
        assert status == "warn"
        assert "无效" in msg or "过期" in msg

    def test_api_server_error(self, channel, monkeypatch):
        monkeypatch.setenv("XQUIK_API_KEY", "xk_test_key")

        def raise_500(req, timeout=None):
            raise urllib.error.HTTPError(url="", code=500, msg="Server Error", hdrs={}, fp=None)

        monkeypatch.setattr(urllib.request, "urlopen", raise_500)
        status, msg = channel.check()
        assert status == "warn"
        assert "500" in msg

    def test_api_network_error(self, channel, monkeypatch):
        monkeypatch.setenv("XQUIK_API_KEY", "xk_test_key")

        def raise_conn(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", raise_conn)
        status, msg = channel.check()
        assert status == "warn"
        assert "连接失败" in msg

    def test_api_empty_trends(self, channel, monkeypatch):
        monkeypatch.setenv("XQUIK_API_KEY", "xk_test_key")

        fake_response = json.dumps({"trends": []}).encode()

        class FakeResp:
            def read(self):
                return fake_response

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResp())
        status, msg = channel.check()
        assert status == "warn"
        assert "空" in msg


# ------------------------------------------------------------------ #
# search_tweets
# ------------------------------------------------------------------ #


class TestSearchTweets:
    def test_basic_search(self, channel, monkeypatch):
        monkeypatch.setenv("XQUIK_API_KEY", "xk_test")
        api_response = {
            "tweets": [
                {
                    "id": "111",
                    "text": "Hello world",
                    "createdAt": "2025-01-01T00:00:00Z",
                    "likeCount": 10,
                    "retweetCount": 2,
                    "replyCount": 1,
                    "quoteCount": 0,
                    "viewCount": 500,
                    "bookmarkCount": 3,
                    "author": {
                        "id": "999",
                        "username": "testuser",
                        "name": "Test",
                        "verified": False,
                    },
                }
            ],
            "has_next_page": False,
            "next_cursor": None,
        }

        class FakeResp:
            def read(self):
                return json.dumps(api_response).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResp())
        result = channel.search_tweets("test query", limit=10)
        assert len(result["tweets"]) == 1
        assert result["tweets"][0]["text"] == "Hello world"
        assert result["tweets"][0]["author"]["username"] == "testuser"
        assert result["has_next_page"] is False

    def test_limit_capped_at_200(self, channel, monkeypatch):
        monkeypatch.setenv("XQUIK_API_KEY", "xk_test")
        captured_urls = []

        class FakeResp:
            def read(self):
                return json.dumps({"tweets": [], "has_next_page": False}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def capture_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            return FakeResp()

        monkeypatch.setattr(urllib.request, "urlopen", capture_urlopen)
        channel.search_tweets("test", limit=500)
        assert "limit=200" in captured_urls[0]

    def test_pagination_cursor(self, channel, monkeypatch):
        monkeypatch.setenv("XQUIK_API_KEY", "xk_test")
        captured_urls = []

        class FakeResp:
            def read(self):
                return json.dumps(
                    {"tweets": [], "has_next_page": False, "next_cursor": None}
                ).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def capture_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            return FakeResp()

        monkeypatch.setattr(urllib.request, "urlopen", capture_urlopen)
        channel.search_tweets("test", cursor="DAACCgACGR")
        assert "cursor=DAACCgACGR" in captured_urls[0]


# ------------------------------------------------------------------ #
# get_tweet
# ------------------------------------------------------------------ #


class TestGetTweet:
    def test_get_tweet_by_id(self, channel, monkeypatch):
        monkeypatch.setenv("XQUIK_API_KEY", "xk_test")
        api_response = {
            "id": "123456",
            "text": "A tweet",
            "createdAt": "2025-06-01T12:00:00Z",
            "likeCount": 42,
            "retweetCount": 5,
            "replyCount": 3,
            "quoteCount": 1,
            "viewCount": 1500,
            "bookmarkCount": 2,
            "author": {
                "id": "789",
                "username": "poster",
                "name": "Poster",
                "followers": 1000,
                "verified": True,
                "profilePicture": "https://example.com/pic.jpg",
            },
        }

        class FakeResp:
            def read(self):
                return json.dumps(api_response).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        captured_urls = []

        def capture_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            return FakeResp()

        monkeypatch.setattr(urllib.request, "urlopen", capture_urlopen)
        tweet = channel.get_tweet("123456")
        assert tweet["id"] == "123456"
        assert tweet["author"]["verified"] is True
        assert "/x/tweets/123456" in captured_urls[0]


# ------------------------------------------------------------------ #
# search_users
# ------------------------------------------------------------------ #


class TestSearchUsers:
    def test_search_users(self, channel, monkeypatch):
        monkeypatch.setenv("XQUIK_API_KEY", "xk_test")
        api_response = {
            "users": [
                {
                    "id": "100",
                    "username": "openai",
                    "name": "OpenAI",
                    "description": "AI research lab",
                    "followers": 5000000,
                    "following": 50,
                    "verified": True,
                }
            ],
            "has_next_page": False,
            "next_cursor": None,
        }

        class FakeResp:
            def read(self):
                return json.dumps(api_response).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResp())
        result = channel.search_users("OpenAI")
        assert len(result["users"]) == 1
        assert result["users"][0]["username"] == "openai"
        assert result["users"][0]["verified"] is True


# ------------------------------------------------------------------ #
# get_user
# ------------------------------------------------------------------ #


class TestGetUser:
    def test_get_user_by_username(self, channel, monkeypatch):
        monkeypatch.setenv("XQUIK_API_KEY", "xk_test")
        api_response = {
            "id": "200",
            "username": "elonmusk",
            "name": "Elon Musk",
            "description": "Mars",
            "followers": 150000000,
            "following": 500,
            "verified": True,
        }

        class FakeResp:
            def read(self):
                return json.dumps(api_response).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        captured_urls = []

        def capture_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            return FakeResp()

        monkeypatch.setattr(urllib.request, "urlopen", capture_urlopen)
        user = channel.get_user("elonmusk")
        assert user["username"] == "elonmusk"
        assert user["followers"] == 150000000
        assert "/x/users/elonmusk" in captured_urls[0]


# ------------------------------------------------------------------ #
# get_trends
# ------------------------------------------------------------------ #


class TestGetTrends:
    def test_get_global_trends(self, channel, monkeypatch):
        monkeypatch.setenv("XQUIK_API_KEY", "xk_test")
        api_response = {
            "trends": [
                {
                    "name": "#AI",
                    "description": "Artificial intelligence",
                    "query": "%23AI",
                    "rank": 1,
                },
                {"name": "#Python", "description": "", "query": "%23Python", "rank": 2},
            ],
            "total": 2,
            "woeid": 1,
        }

        class FakeResp:
            def read(self):
                return json.dumps(api_response).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResp())
        trends = channel.get_trends(woeid=1, count=10)
        assert len(trends) == 2
        assert trends[0]["name"] == "#AI"
        assert trends[1]["rank"] == 2

    def test_count_capped_at_50(self, channel, monkeypatch):
        monkeypatch.setenv("XQUIK_API_KEY", "xk_test")
        captured_urls = []

        class FakeResp:
            def read(self):
                return json.dumps({"trends": []}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def capture_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            return FakeResp()

        monkeypatch.setattr(urllib.request, "urlopen", capture_urlopen)
        channel.get_trends(count=999)
        assert "count=50" in captured_urls[0]


# ------------------------------------------------------------------ #
# _get_json internals
# ------------------------------------------------------------------ #


class TestGetJson:
    def test_sends_api_key_header(self, monkeypatch):
        monkeypatch.setenv("XQUIK_API_KEY", "xk_secret_key")
        captured_requests = []

        class FakeResp:
            def read(self):
                return b'{"ok": true}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def capture_urlopen(req, timeout=None):
            captured_requests.append(req)
            return FakeResp()

        monkeypatch.setattr(urllib.request, "urlopen", capture_urlopen)
        _get_json("/test")
        assert captured_requests[0].get_header("X-api-key") == "xk_secret_key"

    def test_skips_none_params(self, monkeypatch):
        monkeypatch.setenv("XQUIK_API_KEY", "xk_test")
        captured_urls = []

        class FakeResp:
            def read(self):
                return b'{"ok": true}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def capture_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            return FakeResp()

        monkeypatch.setattr(urllib.request, "urlopen", capture_urlopen)
        _get_json("/test", {"q": "hello", "cursor": None})
        assert "cursor" not in captured_urls[0]
        assert "q=hello" in captured_urls[0]


# ------------------------------------------------------------------ #
# Channel metadata
# ------------------------------------------------------------------ #


class TestMetadata:
    def test_name(self, channel):
        assert channel.name == "xquik"

    def test_tier(self, channel):
        assert channel.tier == 1

    def test_backends(self, channel):
        assert channel.backends == ["Xquik API"]

    def test_description_nonempty(self, channel):
        assert channel.description

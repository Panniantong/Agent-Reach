# -*- coding: utf-8 -*-
"""Tests for channel registry basics and health checks."""

import json
import shutil
import subprocess
from urllib.error import URLError

from agent_reach.channels import get_all_channels, get_channel
from agent_reach.channels.xiaohongshu import XiaoHongShuChannel
from agent_reach.channels.xueqiu import XueqiuChannel
from agent_reach.channels.v2ex import V2EXChannel


class TestChannelRegistry:
    def test_get_channel_by_name(self):
        ch = get_channel("github")
        assert ch is not None
        assert ch.name == "github"

    def test_get_unknown_channel_returns_none(self):
        assert get_channel("not-exists") is None

    def test_all_channels_registered(self):
        channels = get_all_channels()
        names = [ch.name for ch in channels]
        assert "web" in names
        assert "github" in names
        assert "twitter" in names
        assert "v2ex" in names


class TestV2EXChannel:
    def test_can_handle_v2ex_urls(self):
        ch = V2EXChannel()
        assert ch.can_handle("https://www.v2ex.com/t/1234567")
        assert ch.can_handle("https://v2ex.com/go/python")
        assert not ch.can_handle("https://github.com/user/repo")
        assert not ch.can_handle("https://reddit.com/r/Python")

    def test_check_ok_when_api_reachable(self, monkeypatch):
        import urllib.request

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return b"[]"

        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda req, timeout=None: FakeResponse(),
        )
        status, msg = V2EXChannel().check()
        assert status == "ok"
        assert "公开 API 可用" in msg

    def test_check_warn_when_api_unreachable(self, monkeypatch):
        import urllib.request

        def raise_error(req, timeout=None):
            raise URLError("connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", raise_error)
        status, msg = V2EXChannel().check()
        assert status == "warn"
        assert "失败" in msg

    # ------------------------------------------------------------------ #
    # get_hot_topics
    # ------------------------------------------------------------------ #

    def test_get_hot_topics_returns_list(self, monkeypatch):
        import urllib.request

        fake_data = [
            {
                "id": 111,
                "title": "Python 3.13 发布了",
                "url": "https://www.v2ex.com/t/111",
                "replies": 42,
                "content": "发布公告内容",
                "created": 1700000000,
                "node": {"name": "python", "title": "Python"},
            },
            {
                "id": 222,
                "title": "Rust 好学吗",
                "url": "https://www.v2ex.com/t/222",
                "replies": 10,
                "content": "",
                "created": 1700000001,
                "node": {"name": "rust", "title": "Rust"},
            },
        ]

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps(fake_data).encode()

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())
        topics = V2EXChannel().get_hot_topics(limit=5)
        assert len(topics) == 2
        assert topics[0]["id"] == 111
        assert topics[0]["title"] == "Python 3.13 发布了"
        assert topics[0]["replies"] == 42
        assert topics[0]["node_name"] == "python"
        assert topics[0]["node_title"] == "Python"
        assert topics[0]["created"] == 1700000000

    def test_get_hot_topics_respects_limit(self, monkeypatch):
        import urllib.request

        fake_data = [
            {"id": i, "title": f"Topic {i}", "url": f"https://v2ex.com/t/{i}", "replies": i,
             "content": "", "created": 1700000000 + i, "node": {"name": "tech", "title": "Tech"}}
            for i in range(10)
        ]

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps(fake_data).encode()

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())
        topics = V2EXChannel().get_hot_topics(limit=3)
        assert len(topics) == 3

    def test_get_hot_topics_truncates_content(self, monkeypatch):
        import urllib.request

        long_content = "A" * 300
        fake_data = [
            {"id": 1, "title": "Long post", "url": "https://v2ex.com/t/1", "replies": 0,
             "content": long_content, "created": 1700000000, "node": {"name": "tech", "title": "Tech"}}
        ]

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps(fake_data).encode()

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())
        topics = V2EXChannel().get_hot_topics(limit=1)
        assert len(topics[0]["content"]) == 200

    # ------------------------------------------------------------------ #
    # get_node_topics
    # ------------------------------------------------------------------ #

    def test_get_node_topics(self, monkeypatch):
        import urllib.request

        fake_data = [
            {
                "id": 333,
                "title": "Flask 部署问题",
                "url": "https://www.v2ex.com/t/333",
                "replies": 5,
                "content": "求帮助",
                "created": 1710000000,
                "node": {"name": "python", "title": "Python"},
            }
        ]

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps(fake_data).encode()

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())
        topics = V2EXChannel().get_node_topics("python")
        assert len(topics) == 1
        assert topics[0]["id"] == 333
        assert topics[0]["node_name"] == "python"
        assert topics[0]["title"] == "Flask 部署问题"
        assert topics[0]["created"] == 1710000000

    # ------------------------------------------------------------------ #
    # get_topic
    # ------------------------------------------------------------------ #

    def test_get_topic_returns_detail_and_replies(self, monkeypatch):
        import urllib.request

        topic_data = [
            {
                "id": 999,
                "title": "测试帖子",
                "url": "https://www.v2ex.com/t/999",
                "content": "帖子正文",
                "replies": 2,
                "node": {"name": "qna", "title": "问与答"},
                "member": {"username": "alice"},
                "created": 1700000000,
            }
        ]
        replies_data = [
            {
                "member": {"username": "bob"},
                "content": "第一条回复",
                "created": 1700000100,
            },
            {
                "member": {"username": "carol"},
                "content": "第二条回复",
                "created": 1700000200,
            },
        ]

        call_count = {"n": 0}

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps(self._payload).encode()

        def fake_urlopen(req, timeout=None):
            url = req.full_url
            if "replies" in url:
                return FakeResponse(replies_data)
            return FakeResponse(topic_data)

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        result = V2EXChannel().get_topic(999)

        assert result["id"] == 999
        assert result["title"] == "测试帖子"
        assert result["author"] == "alice"
        assert result["node_name"] == "qna"
        assert len(result["replies"]) == 2
        assert result["replies"][0]["author"] == "bob"
        assert result["replies"][1]["content"] == "第二条回复"

    def test_get_topic_handles_empty_replies(self, monkeypatch):
        import urllib.request

        topic_data = [
            {
                "id": 1,
                "title": "孤独帖子",
                "url": "https://www.v2ex.com/t/1",
                "content": "",
                "replies": 0,
                "node": {"name": "offtopic", "title": "水"},
                "member": {"username": "dave"},
                "created": 0,
            }
        ]

        class FakeResponse:
            def __init__(self, payload): self._payload = payload
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps(self._payload).encode()

        def fake_urlopen(req, timeout=None):
            if "replies" in req.full_url:
                return FakeResponse([])
            return FakeResponse(topic_data)

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        result = V2EXChannel().get_topic(1)
        assert result["replies"] == []

    # ------------------------------------------------------------------ #
    # get_user
    # ------------------------------------------------------------------ #

    def test_get_user_returns_profile(self, monkeypatch):
        import urllib.request

        fake_user = {
            "id": 42,
            "username": "alice",
            "url": "https://www.v2ex.com/member/alice",
            "website": "https://alice.dev",
            "twitter": "alice_tw",
            "psn": "",
            "github": "alice",
            "btc": "",
            "location": "Shanghai",
            "bio": "Python dev",
            "avatar_large": "https://cdn.v2ex.com/avatars/alice_large.png",
            "created": 1500000000,
        }

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps(fake_user).encode()

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())
        user = V2EXChannel().get_user("alice")

        assert user["id"] == 42
        assert user["username"] == "alice"
        assert user["github"] == "alice"
        assert user["location"] == "Shanghai"
        assert "alice_large.png" in user["avatar"]

    # ------------------------------------------------------------------ #
    # search
    # ------------------------------------------------------------------ #

    def test_search_returns_unavailable_notice(self):
        result = V2EXChannel().search("python asyncio")
        assert len(result) == 1
        assert "error" in result[0]
        assert "V2EX" in result[0]["error"]


class TestXueqiuChannel:
    def test_can_handle_xueqiu_urls(self):
        ch = XueqiuChannel()
        assert ch.can_handle("https://xueqiu.com/S/SH600519")
        assert ch.can_handle("https://stock.xueqiu.com/v5/stock/batch/quote.json")
        assert ch.can_handle("https://www.xueqiu.com/1234567890/12345")
        assert not ch.can_handle("https://github.com/user/repo")
        assert not ch.can_handle("https://v2ex.com/t/123")

    def test_check_ok_when_api_reachable(self, monkeypatch):
        import agent_reach.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)

        fake_response_data = {
            "data": {
                "items": [
                    {"quote": {"symbol": "SH000001", "name": "上证指数", "current": 3200.0}}
                ]
            }
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps(fake_response_data).encode()

        monkeypatch.setattr(xueqiu_mod._opener, "open", lambda req, timeout=None: FakeResponse())
        status, msg = XueqiuChannel().check()
        assert status == "ok"
        assert "公开 API 可用" in msg

    def test_check_warn_when_api_unreachable(self, monkeypatch):
        import agent_reach.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)

        def raise_error(req, timeout=None):
            raise URLError("connection refused")

        monkeypatch.setattr(xueqiu_mod._opener, "open", raise_error)
        status, msg = XueqiuChannel().check()
        assert status == "warn"
        assert "失败" in msg

    # ------------------------------------------------------------------ #
    # get_stock_quote
    # ------------------------------------------------------------------ #

    def test_get_stock_quote(self, monkeypatch):
        import agent_reach.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)

        fake_data = {
            "data": {
                "items": [
                    {
                        "quote": {
                            "symbol": "SH600519",
                            "name": "贵州茅台",
                            "current": 1800.0,
                            "percent": 1.5,
                            "chg": 26.6,
                            "high": 1810.0,
                            "low": 1770.0,
                            "open": 1775.0,
                            "last_close": 1773.4,
                            "volume": 12345678,
                            "amount": 22000000000,
                            "market_capital": 2260000000000,
                            "turnover_rate": 0.098,
                            "pe_ttm": 30.5,
                            "timestamp": 1700000000000,
                        }
                    }
                ]
            }
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps(fake_data).encode()

        monkeypatch.setattr(xueqiu_mod._opener, "open", lambda req, timeout=None: FakeResponse())
        quote = XueqiuChannel().get_stock_quote("SH600519")
        assert quote["symbol"] == "SH600519"
        assert quote["name"] == "贵州茅台"
        assert quote["current"] == 1800.0
        assert quote["percent"] == 1.5
        assert quote["volume"] == 12345678

    # ------------------------------------------------------------------ #
    # search_stock
    # ------------------------------------------------------------------ #

    def test_search_stock(self, monkeypatch):
        import agent_reach.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)

        fake_data = {
            "stocks": [
                {"code": "SH600519", "name": "贵州茅台", "exchange": "SHA"},
                {"code": "SZ000858", "name": "五粮液", "exchange": "SZA"},
            ]
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps(fake_data).encode()

        monkeypatch.setattr(xueqiu_mod._opener, "open", lambda req, timeout=None: FakeResponse())
        results = XueqiuChannel().search_stock("茅台", limit=5)
        assert len(results) == 2
        assert results[0]["symbol"] == "SH600519"
        assert results[0]["name"] == "贵州茅台"
        assert results[1]["exchange"] == "SZA"

    # ------------------------------------------------------------------ #
    # get_hot_posts
    # ------------------------------------------------------------------ #

    def test_get_hot_posts_returns_list(self, monkeypatch):
        import agent_reach.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)

        fake_data = {
            "data": {
                "items": [
                    {
                        "original_status": {
                            "id": 111,
                            "title": "市场分析",
                            "text": "<p>今天大盘走势&amp;分析</p>",
                            "user": {"screen_name": "投资者A"},
                            "like_count": 42,
                            "target": "/1234567890/111",
                        }
                    },
                    {
                        "original_status": {
                            "id": 222,
                            "title": "",
                            "text": "短评",
                            "user": {"screen_name": "投资者B"},
                            "like_count": 10,
                            "target": "/9876543210/222",
                        }
                    },
                ]
            }
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps(fake_data).encode()

        monkeypatch.setattr(xueqiu_mod._opener, "open", lambda req, timeout=None: FakeResponse())
        posts = XueqiuChannel().get_hot_posts(limit=10)
        assert len(posts) == 2
        assert posts[0]["id"] == 111
        assert posts[0]["author"] == "投资者A"
        assert posts[0]["likes"] == 42
        assert "今天大盘走势&分析" in posts[0]["text"]  # HTML stripped
        assert "<p>" not in posts[0]["text"]
        assert posts[0]["url"] == "https://xueqiu.com/1234567890/111"

    def test_get_hot_posts_respects_limit(self, monkeypatch):
        import agent_reach.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)

        fake_data = {
            "data": {
                "items": [
                    {
                        "original_status": {
                            "id": i,
                            "title": f"Post {i}",
                            "text": f"Content {i}",
                            "user": {"screen_name": f"User {i}"},
                            "like_count": i,
                            "target": f"/user/{i}",
                        }
                    }
                    for i in range(10)
                ]
            }
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps(fake_data).encode()

        monkeypatch.setattr(xueqiu_mod._opener, "open", lambda req, timeout=None: FakeResponse())
        posts = XueqiuChannel().get_hot_posts(limit=3)
        assert len(posts) == 3

    # ------------------------------------------------------------------ #
    # get_hot_stocks
    # ------------------------------------------------------------------ #

    def test_get_hot_stocks(self, monkeypatch):
        import agent_reach.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)

        fake_data = {
            "data": {
                "items": [
                    {"code": "SH600519", "name": "贵州茅台", "current": 1800.0, "percent": 1.5},
                    {"code": "SZ000858", "name": "五粮液", "current": 160.0, "percent": -0.8},
                    {"code": "SH601318", "name": "中国平安", "current": 45.0, "percent": 0.3},
                ]
            }
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps(fake_data).encode()

        monkeypatch.setattr(xueqiu_mod._opener, "open", lambda req, timeout=None: FakeResponse())
        stocks = XueqiuChannel().get_hot_stocks(limit=10, stock_type=10)
        assert len(stocks) == 3
        assert stocks[0]["symbol"] == "SH600519"
        assert stocks[0]["rank"] == 1
        assert stocks[1]["percent"] == -0.8
        assert stocks[2]["rank"] == 3


class TestXiaoHongShuChannel:
    def test_reports_ok_when_server_health_is_ok(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _: "/opt/homebrew/bin/mcporter")

        def fake_run(cmd, **kwargs):
            if cmd[:4] == ["/opt/homebrew/bin/mcporter", "config", "get", "xiaohongshu"]:
                return subprocess.CompletedProcess(cmd, 0, '{"name":"xiaohongshu"}', "")
            if cmd[:4] == ["/opt/homebrew/bin/mcporter", "list", "xiaohongshu", "--json"]:
                return subprocess.CompletedProcess(cmd, 0, '{"status": "ok"}', "")
            raise AssertionError(f"unexpected command: {cmd}")

        monkeypatch.setattr(subprocess, "run", fake_run)

        assert XiaoHongShuChannel().check() == (
            "ok",
            "MCP 已连接（阅读、搜索、发帖、评论、点赞）",
        )

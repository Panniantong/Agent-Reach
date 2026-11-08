# -*- coding: utf-8 -*-
"""Tests for channel registry basics, URL routing and Xueqiu session helpers."""

from agent_reach.channels import get_all_channels, get_channel
from agent_reach.channels.facebook import FacebookChannel
from agent_reach.channels.instagram import InstagramChannel
from agent_reach.channels.v2ex import V2EXChannel
from agent_reach.channels.xueqiu import XueqiuChannel


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
        assert "facebook" in names
        assert "instagram" in names
        assert "v2ex" in names



class TestOpenCLISiteChannels:
    def test_facebook_can_handle_common_urls(self):
        ch = FacebookChannel()
        assert ch.can_handle("https://www.facebook.com/zuck")
        assert ch.can_handle("https://m.facebook.com/groups/123")
        assert ch.can_handle("https://fb.com/some-page")
        assert ch.can_handle("https://fb.watch/abc123")
        assert not ch.can_handle("https://instagram.com/openai")

    def test_instagram_can_handle_common_urls(self):
        ch = InstagramChannel()
        assert ch.can_handle("https://www.instagram.com/openai/")
        assert ch.can_handle("https://instagram.com/p/abc123/")
        assert ch.can_handle("https://instagr.am/p/abc123/")
        assert not ch.can_handle("https://facebook.com/openai")



class TestV2EXChannel:
    def test_can_handle_v2ex_urls(self):
        ch = V2EXChannel()
        assert ch.can_handle("https://www.v2ex.com/t/1234567")
        assert ch.can_handle("https://v2ex.com/go/python")
        assert not ch.can_handle("https://github.com/user/repo")
        assert not ch.can_handle("https://reddit.com/r/Python")


class TestXueqiuChannel:
    def test_can_handle_xueqiu_urls(self):
        ch = XueqiuChannel()
        assert ch.can_handle("https://xueqiu.com/S/SH600519")
        assert ch.can_handle("https://stock.xueqiu.com/v5/stock/batch/quote.json")
        assert ch.can_handle("https://www.xueqiu.com/1234567890/12345")
        assert not ch.can_handle("https://github.com/user/repo")
        assert not ch.can_handle("https://v2ex.com/t/123")

    def test_ensure_cookies_loads_from_config(self, monkeypatch, tmp_path):
        """_ensure_cookies() should inject cookies from the config file."""
        import agent_reach.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", False)

        # Provide a fake Config that returns a cookie string with xq_a_token
        class FakeConfig:
            def get(self, key, default=None):
                if key == "xueqiu_cookie":
                    return "xq_a_token=TESTTOKEN; xq_is_login=1"
                return default

        import agent_reach.channels.xueqiu as xq_mod
        monkeypatch.setattr(
            xq_mod,
            "_load_cookies_from_config",
            lambda config=None: (
                xq_mod._inject_cookie_string(
                    "xq_a_token=TESTTOKEN; xq_is_login=1"
                )
                or True
            ),
        )

        # Patch opener so no real HTTP call is made
        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return b'{"data":{"items":[]}}'

        monkeypatch.setattr(xq_mod._opener, "open", lambda req, timeout=None: FakeResp())

        xq_mod._ensure_cookies()
        assert xq_mod._cookies_initialized is True
        cookie_names = {c.name for c in xq_mod._cookie_jar}
        assert "xq_a_token" in cookie_names

    def test_ensure_cookies_uses_public_homepage_fallback(self, monkeypatch):
        import agent_reach.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", False)
        monkeypatch.setattr(
            xueqiu_mod,
            "_load_cookies_from_config",
            lambda config=None: False,
        )
        requested = []

        class FakeResponse:
            pass

        monkeypatch.setattr(
            xueqiu_mod._opener,
            "open",
            lambda req, timeout=None: requested.append(req.full_url) or FakeResponse(),
        )
        xueqiu_mod._ensure_cookies()

        assert requested == ["https://xueqiu.com"]
        assert xueqiu_mod._cookies_initialized is True

    def test_get_json_sends_referer_and_browser_ua(self, monkeypatch):
        """_get_json() must send Referer and a browser-like User-Agent."""
        import agent_reach.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)
        captured = {}

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return b'{"data":{"items":[]}}'

        def fake_open(req, timeout=None):
            captured["ua"] = req.get_header("User-agent")
            captured["referer"] = req.get_header("Referer")
            return FakeResp()

        monkeypatch.setattr(xueqiu_mod._opener, "open", fake_open)
        xueqiu_mod._get_json("https://stock.xueqiu.com/v5/stock/batch/quote.json?symbol=SH000001")

        assert captured["referer"] == "https://xueqiu.com/"
        assert "Mozilla" in captured["ua"]
        assert "agent-reach" not in captured["ua"]



class TestRedditChannel:
    def test_can_handle_reddit_urls(self):
        from agent_reach.channels.reddit import RedditChannel
        ch = RedditChannel()
        assert ch.can_handle("https://www.reddit.com/r/python/comments/abc123/")
        assert ch.can_handle("https://redd.it/abc123")
        assert not ch.can_handle("https://github.com/user/repo")
        assert not ch.can_handle("https://v2ex.com/t/123")

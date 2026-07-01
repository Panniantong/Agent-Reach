# -*- coding: utf-8 -*-
"""Browser cookie import must be scoped to the requested channels.

Regression for cookie overcollection: `configure --from-browser` (and the
install-time auto-import) previously harvested and persisted cookies for
EVERY supported platform regardless of which channels the user asked for.
Importing --channels twitter must not read or save XHS/Bilibili/Xueqiu
cookies.
"""

import sys
import types

import pytest

import agent_reach.cookie_extract as ce


@pytest.fixture
def fake_browser(monkeypatch):
    """Inject a fake rookiepy whose chrome() returns cookies for all 4 platforms."""
    cookies = [
        {"name": "auth_token", "value": "TW_AUTH", "domain": ".x.com"},
        {"name": "ct0", "value": "TW_CT0", "domain": ".x.com"},
        {"name": "web_session", "value": "XHS_SESS", "domain": ".xiaohongshu.com"},
        {"name": "a1", "value": "XHS_A1", "domain": ".xiaohongshu.com"},
        {"name": "SESSDATA", "value": "BILI_SESS", "domain": ".bilibili.com"},
        {"name": "bili_jct", "value": "BILI_JCT", "domain": ".bilibili.com"},
        {"name": "xq_a_token", "value": "XQ_TOKEN", "domain": ".xueqiu.com"},
    ]
    def jar():
        return list(cookies)

    fake = types.SimpleNamespace(
        chrome=jar, firefox=jar, edge=jar, brave=jar, opera=jar
    )
    monkeypatch.setitem(sys.modules, "rookiepy", fake)
    # Silence best-effort file syncs so tests don't touch the real home dir.
    monkeypatch.setattr(ce, "_sync_xfetch_session", lambda *a, **k: None)
    monkeypatch.setattr(ce, "_sync_bird_env", lambda *a, **k: None)
    return fake


class FakeConfig:
    def __init__(self):
        self.data = {}

    def set(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)


class TestResolveCookieTargets:
    def test_maps_xiaohongshu_alias_to_xhs(self):
        assert ce.resolve_cookie_targets({"xiaohongshu"}) == {"xhs"}

    def test_direct_config_keys_pass_through(self):
        assert ce.resolve_cookie_targets({"twitter", "bilibili"}) == {"twitter", "bilibili"}

    def test_all_expands_to_every_cookie_platform(self):
        assert ce.resolve_cookie_targets({"all"}) == {"twitter", "xhs", "bilibili", "xueqiu"}

    def test_non_cookie_channels_are_dropped(self):
        assert ce.resolve_cookie_targets({"twitter", "reddit", "youtube"}) == {"twitter"}

    def test_empty_selection(self):
        assert ce.resolve_cookie_targets(set()) == set()


class TestExtractAllScope:
    def test_only_requested_platform_extracted(self, fake_browser):
        result = ce.extract_all("chrome", config_keys={"twitter"})
        assert set(result) == {"twitter"}

    def test_no_scope_extracts_everything(self, fake_browser):
        result = ce.extract_all("chrome")
        assert {"twitter", "xhs", "bilibili", "xueqiu"} <= set(result)

    def test_lookalike_cookie_domain_not_swept_in(self, monkeypatch):
        """A cookie from a lookalike host (notxueqiu.com) must not be pulled
        into the Xueqiu cookie string."""
        cookies = [
            {"name": "xq_a_token", "value": "REAL", "domain": ".xueqiu.com"},
            {"name": "session", "value": "SUB", "domain": "stock.xueqiu.com"},
            {"name": "evil", "value": "ATTACKER", "domain": "notxueqiu.com"},
        ]
        fake = types.SimpleNamespace(
            chrome=lambda: list(cookies), firefox=lambda: list(cookies),
            edge=lambda: list(cookies), brave=lambda: list(cookies),
            opera=lambda: list(cookies),
        )
        monkeypatch.setitem(sys.modules, "rookiepy", fake)
        result = ce.extract_all("chrome", config_keys={"xueqiu"})
        cookie_str = result["xueqiu"]["cookie_string"]
        assert "xq_a_token=REAL" in cookie_str
        assert "session=SUB" in cookie_str  # real subdomain kept
        assert "evil" not in cookie_str     # lookalike rejected


class TestConfigureFromBrowserScope:
    def test_twitter_only_does_not_save_other_platforms(self, fake_browser):
        cfg = FakeConfig()
        ce.configure_from_browser("chrome", cfg, {"twitter"})
        assert cfg.data.get("twitter_auth_token") == "TW_AUTH"
        assert cfg.data.get("twitter_ct0") == "TW_CT0"
        # Overcollection guard: nothing else may be persisted.
        assert "xhs_cookie" not in cfg.data
        assert "bilibili_sessdata" not in cfg.data
        assert "xueqiu_cookie" not in cfg.data

    def test_empty_targets_saves_nothing(self, fake_browser):
        cfg = FakeConfig()
        ce.configure_from_browser("chrome", cfg, set())
        assert cfg.data == {}

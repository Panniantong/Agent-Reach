# -*- coding: utf-8 -*-
"""Dedicated tests for the ``douyin`` channel.

Douyin's readiness is layered like YouTube's: yt-dlp must probe alive
(missing / broken / unrunnable are distinct), and on top of that Douyin's
risk control demands cookies — so a healthy yt-dlp without a configured
cookie source is ``warn``, not ``ok``. These tests stub ``probe_command``
so every branch runs offline.
"""

from unittest.mock import patch

from agent_reach.channels import douyin as dy
from agent_reach.channels.douyin import DouyinChannel, douyin_cookie_args
from agent_reach.probe import ProbeResult


class _Cfg:
    """Minimal config stand-in: just the ``get`` the channel uses."""

    def __init__(self, data):
        self._d = data

    def get(self, key, default=None):
        return self._d.get(key, default)


# --- can_handle / is_douyin_url ---

def test_can_handle_matches_douyin_hosts():
    ch = DouyinChannel()
    for url in [
        "https://www.douyin.com/video/7653652590353321258",
        "https://www.douyin.com/user/self?modal_id=7653652590353321258",
        "https://v.douyin.com/abcDEF/",
        "https://www.iesdouyin.com/share/video/123",
        "https://DOUYIN.COM/video/123",
    ]:
        assert ch.can_handle(url) is True, url
    for url in [
        "https://example.com",
        "https://www.youtube.com/watch?v=abc",
        "https://bilibili.com/video/BV1xx",
        "",
    ]:
        assert ch.can_handle(url) is False, url


# --- douyin_cookie_args ---

def test_cookie_args_empty_without_config():
    assert douyin_cookie_args(None) == []
    assert douyin_cookie_args(_Cfg({})) == []


def test_cookie_args_browser_source_wins():
    cfg = _Cfg({"douyin_cookies_from": "chrome", "douyin_cookies": "sessionid=x"})
    assert douyin_cookie_args(cfg) == ["--cookies-from-browser", "chrome"]


def test_cookie_args_header_string_fallback():
    cfg = _Cfg({"douyin_cookies": "sessionid=x; msToken=y"})
    assert douyin_cookie_args(cfg) == ["--add-headers", "Cookie:sessionid=x; msToken=y"]


# --- check ---

def test_check_off_when_yt_dlp_missing():
    ch = DouyinChannel()
    with patch.object(dy, "probe_command", return_value=ProbeResult("missing")):
        status, msg = ch.check(_Cfg({}))
    assert status == "off"
    assert ch.active_backend is None


def test_check_error_when_yt_dlp_broken():
    ch = DouyinChannel()
    with patch.object(dy, "probe_command",
                      return_value=ProbeResult("broken", hint="relink venv")):
        status, msg = ch.check(_Cfg({}))
    assert status == "error"
    assert "relink venv" in msg
    assert ch.active_backend is None


def test_check_error_when_yt_dlp_unrunnable():
    ch = DouyinChannel()
    with patch.object(dy, "probe_command",
                      return_value=ProbeResult("timeout", hint="too slow")):
        status, msg = ch.check(_Cfg({}))
    assert status == "error"
    assert ch.active_backend is None


def test_check_warn_when_yt_dlp_alive_but_no_cookies():
    ch = DouyinChannel()
    with patch.object(dy, "probe_command", return_value=ProbeResult("ok")):
        status, msg = ch.check(_Cfg({}))
    assert status == "warn"
    assert "douyin-cookies" in msg
    # yt-dlp 本体是活的，后端归属不受 Cookie 缺失影响
    assert ch.active_backend == "yt-dlp"


def test_check_warn_without_config_object():
    ch = DouyinChannel()
    with patch.object(dy, "probe_command", return_value=ProbeResult("ok")):
        status, msg = ch.check(None)
    assert status == "warn"
    assert ch.active_backend == "yt-dlp"


def test_check_ok_with_browser_cookie_source():
    ch = DouyinChannel()
    with patch.object(dy, "probe_command", return_value=ProbeResult("ok")):
        status, msg = ch.check(_Cfg({"douyin_cookies_from": "chrome"}))
    assert status == "ok"
    assert ch.active_backend == "yt-dlp"


def test_check_ok_with_header_string_cookies():
    ch = DouyinChannel()
    with patch.object(dy, "probe_command", return_value=ProbeResult("ok")):
        status, msg = ch.check(_Cfg({"douyin_cookies": "sessionid=x"}))
    assert status == "ok"
    assert ch.active_backend == "yt-dlp"


# --- channel metadata ---

def test_channel_metadata():
    ch = DouyinChannel()
    assert ch.name == "douyin"
    assert ch.tier == 1
    assert ch.backends == ["yt-dlp"]


# --- cookie_extract integration ---

def test_platform_specs_include_douyin():
    from agent_reach.cookie_extract import PLATFORM_SPECS

    spec = next(s for s in PLATFORM_SPECS if s["config_key"] == "douyin")
    assert ".douyin.com" in spec["domains"]


class _RecordingCfg(_Cfg):
    def __init__(self):
        super().__init__({})
        self.deleted = []

    def set(self, key, value):
        self._d[key] = value

    def delete(self, key):
        self.deleted.append(key)
        self._d.pop(key, None)


def test_configure_from_browser_saves_douyin_cookies_with_sessionid():
    import agent_reach.cookie_extract as ce

    cfg = _RecordingCfg()
    extracted = {"douyin": {"cookie_string": "sessionid=abc; msToken=xyz"}}
    with patch.object(ce, "extract_all", return_value=extracted):
        results = ce.configure_from_browser("chrome", cfg)

    assert cfg.get("douyin_cookies") == "sessionid=abc; msToken=xyz"
    # 存 header 字符串时清掉浏览器来源，避免两份配置互相覆盖
    assert "douyin_cookies_from" in cfg.deleted
    assert any(name == "Douyin" and ok for name, ok, _ in results)


def test_configure_from_browser_rejects_anonymous_douyin_cookies():
    import agent_reach.cookie_extract as ce

    cfg = _RecordingCfg()
    extracted = {"douyin": {"cookie_string": "ttwid=anon; msToken=xyz"}}
    with patch.object(ce, "extract_all", return_value=extracted):
        results = ce.configure_from_browser("chrome", cfg)

    assert cfg.get("douyin_cookies") is None
    assert any(name == "Douyin" and not ok for name, ok, _ in results)

"""Least-privilege browser-cookie extraction and URL routing regressions."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from agent_reach import cookie_extract


class RecordingConfig:
    def __init__(self):
        self.values = {}

    def set(self, key, value):
        self.values[key] = value


def test_browser_extraction_requires_an_explicit_platform():
    with pytest.raises(ValueError, match="platform"):
        cookie_extract.extract_all("chrome")


def test_rookiepy_is_limited_at_source_to_the_requested_platform(monkeypatch):
    calls = []

    def chrome(domains):
        calls.append(domains)
        return [
            {"name": "SESSDATA", "value": "session", "domain": ".bilibili.com"},
            {"name": "bili_jct", "value": "csrf", "domain": ".bilibili.com"},
        ]

    fake_rookiepy = SimpleNamespace(
        chrome=chrome,
        firefox=lambda domains: [],
        edge=lambda domains: [],
        brave=lambda domains: [],
        opera=lambda domains: [],
    )
    monkeypatch.setitem(sys.modules, "rookiepy", fake_rookiepy)

    extracted = cookie_extract.extract_all("chrome", platform="bilibili")

    assert calls == [[".bilibili.com"]]
    assert extracted == {
        "bilibili": {"SESSDATA": "session", "bili_jct": "csrf"}
    }


def test_xueqiu_collects_only_xq_a_token(monkeypatch):
    def chrome(domains):
        assert domains == [".xueqiu.com"]
        return [
            {"name": "xq_a_token", "value": "needed", "domain": ".xueqiu.com"},
            {"name": "device_id", "value": "unrelated", "domain": ".xueqiu.com"},
            {"name": "remember", "value": "private", "domain": ".xueqiu.com"},
        ]

    fake_rookiepy = SimpleNamespace(
        chrome=chrome,
        firefox=lambda domains: [],
        edge=lambda domains: [],
        brave=lambda domains: [],
        opera=lambda domains: [],
    )
    monkeypatch.setitem(sys.modules, "rookiepy", fake_rookiepy)

    extracted = cookie_extract.extract_all("chrome", platform="xueqiu")

    assert extracted == {"xueqiu": {"xq_a_token": "needed"}}


def test_cookie_backend_cannot_smuggle_a_lookalike_domain(monkeypatch):
    def chrome(domains):
        assert domains == [".xueqiu.com"]
        return [
            {"name": "xq_a_token", "value": "valid", "domain": ".xueqiu.com"},
            {
                "name": "xq_a_token",
                "value": "lookalike",
                "domain": ".notxueqiu.com",
            },
        ]

    fake_rookiepy = SimpleNamespace(
        chrome=chrome,
        firefox=lambda domains: [],
        edge=lambda domains: [],
        brave=lambda domains: [],
        opera=lambda domains: [],
    )
    monkeypatch.setitem(sys.modules, "rookiepy", fake_rookiepy)

    extracted = cookie_extract.extract_all("chrome", platform="xueqiu")

    assert extracted == {"xueqiu": {"xq_a_token": "valid"}}


@pytest.mark.parametrize(
    ("platform", "manual_key"),
    [
        ("twitter", "twitter-cookies"),
        ("xhs", "xhs-cookies"),
    ],
)
def test_browser_extraction_rejects_cookie_editor_platforms(platform, manual_key):
    with pytest.raises(ValueError, match=rf"Cookie-Editor.*{manual_key}"):
        cookie_extract.extract_all("chrome", platform=platform)


def test_explicit_profile_uses_only_that_cookie_database(tmp_path, monkeypatch):
    cookie_db = tmp_path / "Profile 1" / "Network" / "Cookies"
    cookie_db.parent.mkdir(parents=True)
    cookie_db.write_bytes(b"test database placeholder")
    monkeypatch.setattr(
        cookie_extract, "_chromium_user_data_dir", lambda browser: tmp_path
    )
    monkeypatch.setitem(sys.modules, "rookiepy", None)

    calls = []

    def chrome(*, cookie_file=None, domain_name=""):
        calls.append((cookie_file, domain_name))
        return []

    fake_browser_cookie3 = SimpleNamespace(
        chrome=chrome,
        firefox=lambda **kwargs: [],
        edge=lambda **kwargs: [],
        brave=lambda **kwargs: [],
        opera=lambda **kwargs: [],
    )
    monkeypatch.setitem(sys.modules, "browser_cookie3", fake_browser_cookie3)

    cookie_extract.extract_all(
        "chrome", platform="xueqiu", profile="Profile 1"
    )

    assert calls == [
        (str(cookie_db), ".xueqiu.com"),
    ]


def test_missing_explicit_profile_fails_instead_of_falling_back(tmp_path, monkeypatch):
    default_db = tmp_path / "Default" / "Network" / "Cookies"
    default_db.parent.mkdir(parents=True)
    default_db.write_bytes(b"default profile")
    monkeypatch.setattr(
        cookie_extract, "_chromium_user_data_dir", lambda browser: tmp_path
    )

    with pytest.raises(ValueError, match="Profile 7.*not found"):
        cookie_extract.extract_all(
            "chrome", platform="xueqiu", profile="Profile 7"
        )


def test_configure_requires_platform_before_reading_browser():
    with pytest.raises(ValueError, match="platform"):
        cookie_extract.configure_from_browser("chrome", RecordingConfig())


def test_invalid_platform_error_does_not_echo_url_secrets():
    with pytest.raises(ValueError) as error:
        cookie_extract.extract_all(
            "chrome",
            platform="https://user:pass@example.test/?access_token=secret",
        )

    message = str(error.value)
    assert "user:pass" not in message
    assert "secret" not in message
    assert "***" in message


@pytest.mark.parametrize("platform", ["twitter", "xhs"])
def test_configure_from_browser_rejects_cookie_editor_platforms(platform):
    with pytest.raises(ValueError, match="Cookie-Editor"):
        cookie_extract.configure_from_browser(
            "chrome", RecordingConfig(), platform=platform
        )


def test_xueqiu_config_persists_only_xq_a_token(monkeypatch):
    monkeypatch.setattr(
        cookie_extract,
        "extract_all",
        lambda browser, **kwargs: {"xueqiu": {"xq_a_token": "needed"}},
    )
    config = RecordingConfig()

    result = cookie_extract.configure_from_browser(
        "chrome", config, platform="xueqiu"
    )

    assert config.values == {"xueqiu_cookie": "xq_a_token=needed"}
    assert result[0].targets == ("xueqiu_cookie",)


def test_bilibili_config_reports_each_written_key(monkeypatch):
    monkeypatch.setattr(
        cookie_extract,
        "extract_all",
        lambda browser, **kwargs: {
            "bilibili": {"SESSDATA": "session", "bili_jct": "csrf"}
        },
    )
    config = RecordingConfig()

    result = cookie_extract.configure_from_browser(
        "chrome", config, platform="bilibili"
    )

    assert config.values == {
        "bilibili_sessdata": "session",
        "bilibili_csrf": "csrf",
    }
    assert result[0].targets == ("bilibili_sessdata", "bilibili_csrf")
    assert tuple(result[0]) == ("Bilibili", True, "SESSDATA + bili_jct")

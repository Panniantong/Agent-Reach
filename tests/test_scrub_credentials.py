"""Secrets embedded in URLs must not reach user-facing diagnostics."""

import sys
from types import SimpleNamespace

import pytest

from agent_reach import cookie_extract
from agent_reach.channels import v2ex as v2ex_module
from agent_reach.channels import xueqiu as xueqiu_module
from agent_reach.channels.v2ex import V2EXChannel
from agent_reach.channels.xueqiu import XueqiuChannel
from agent_reach.utils.text import scrub_url_credentials


def test_scrubs_userinfo_and_sensitive_query_values():
    raw = (
        "proxy http://user:pass@proxy.example:8080 failed; "
        "upstream https://api.example.test/path?access_token=secret"
        "&page=2&api_key=another-secret"
    )

    scrubbed = scrub_url_credentials(raw)

    assert "user:pass" not in scrubbed
    assert "secret" not in scrubbed
    assert "another-secret" not in scrubbed
    assert "http://***@proxy.example:8080" in scrubbed
    assert "access_token=***" in scrubbed
    assert "page=2" in scrubbed
    assert "api_key=***" in scrubbed


def test_scrubs_multiple_schemes_and_fragment_tokens():
    raw = (
        "socks5://token@host:1080 "
        "https://example.test/#auth_token=fragment-secret"
    )

    scrubbed = scrub_url_credentials(ValueError(raw))

    assert scrubbed == (
        "socks5://***@host:1080 "
        "https://example.test/#auth_token=***"
    )


def test_scrubs_bare_user_password_host_diagnostics():
    raw = "proxy handshake for user:pass@proxy.test failed"
    assert scrub_url_credentials(raw) == "proxy handshake for ***@proxy.test failed"


def test_leaves_non_secret_urls_and_plain_text_unchanged():
    raw = "See https://example.test/search?q=python&page=2 after timeout"
    assert scrub_url_credentials(raw) == raw


@pytest.mark.parametrize(
    ("module", "channel"),
    [
        (v2ex_module, V2EXChannel()),
        (xueqiu_module, XueqiuChannel()),
    ],
)
def test_channel_health_messages_scrub_url_secrets(module, channel, monkeypatch):
    def fail(_url, *_args, **_kwargs):
        raise RuntimeError(
            "proxy http://user:pass@proxy.test:8080 refused "
            "https://api.test/data?access_token=top-secret"
        )

    monkeypatch.setattr(module, "_get_json", fail)

    _status, message = channel.check()

    assert "user:pass" not in message
    assert "top-secret" not in message
    assert "***" in message


def test_browser_backend_errors_scrub_url_secrets(monkeypatch):
    def chrome(_domains):
        raise RuntimeError(
            "failed via http://user:pass@proxy.test "
            "https://api.test/?token=top-secret"
        )

    fake_rookiepy = SimpleNamespace(
        chrome=chrome,
        firefox=lambda domains: [],
        edge=lambda domains: [],
        brave=lambda domains: [],
        opera=lambda domains: [],
    )
    monkeypatch.setitem(sys.modules, "rookiepy", fake_rookiepy)

    with pytest.raises(RuntimeError) as error:
        cookie_extract.extract_all("chrome", platform="xueqiu")

    message = str(error.value)
    assert "user:pass" not in message
    assert "top-secret" not in message
    assert "***" in message

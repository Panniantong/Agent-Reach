# -*- coding: utf-8 -*-
"""Tests for WebChannel.read — SSRF guard, URL encoding, response cap."""

import io

import pytest

from agent_reach.channels import web as web_mod
from agent_reach.channels.web import WebChannel
from agent_reach.utils.urlsafe import UnsafeURLError


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def _patch_urlopen(monkeypatch, payload: bytes, capture: dict):
    def fake_urlopen(req, timeout=None):
        capture["url"] = req.full_url
        return _FakeResp(payload)

    monkeypatch.setattr(web_mod.urllib.request, "urlopen", fake_urlopen)


def test_rejects_non_http_scheme(monkeypatch):
    monkeypatch.setattr(
        web_mod.urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("must not fetch an unsafe URL"),
    )
    with pytest.raises(UnsafeURLError):
        WebChannel().read("file:///etc/passwd")


def test_rejects_internal_ssrf(monkeypatch):
    monkeypatch.setattr(
        web_mod.urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("must not fetch an internal host"),
    )
    with pytest.raises(UnsafeURLError):
        WebChannel().read("http://169.254.169.254/latest/meta-data/")


def test_bare_host_gets_https_and_is_fetched(monkeypatch):
    capture = {}
    _patch_urlopen(monkeypatch, b"# hello", capture)
    out = WebChannel().read("1.1.1.1/page")
    assert out == "# hello"
    # URL is percent-encoded into the Jina path.
    assert capture["url"].startswith("https://r.jina.ai/")
    assert "https" in capture["url"]


def test_response_is_capped(monkeypatch):
    capture = {}
    big = b"a" * (web_mod._MAX_BYTES + 5000)
    _patch_urlopen(monkeypatch, big, capture)
    out = WebChannel().read("https://1.1.1.1/big")
    assert len(out) == web_mod._MAX_BYTES

# -*- coding: utf-8 -*-
"""Dedicated tests for the ``web`` channel.

``web`` is the tier-0 catch-all: ``can_handle`` must accept *anything* so it
can back-stop every other channel, and ``read`` must normalise the URL before
handing it to the active backend. The channel has two backends — Firecrawl
(preferred, self-hostable) and Jina Reader (always-available public
fallback) — with transport failures falling back and content failures
propagating, per ``base.py``'s ordered-backend contract.
"""

from unittest.mock import MagicMock

import pytest

from agent_reach.channels.web import (
    _DEFAULT_FIRECRAWL_URL,
    _MAX_RESPONSE_BYTES,
    _UA,
    WebChannel,
)


def _resp(body=b"# Example\nfull text\n"):
    """A urlopen() return value usable as a context manager."""
    cm = MagicMock()
    inner = cm.__enter__.return_value
    inner.read.return_value = body
    inner.status = 200
    cm.status = 200
    return cm


def _err(exception):
    """A side_effect that raises the given exception (no args)."""
    def _raise(*_a, **_k):
        raise exception
    return _raise


class _JinaConfig:
    """Config that forces the Jina Reader backend (bypasses Firecrawl)."""

    def get(self, key, default=None):
        if key == "web_backend":
            return "Jina Reader"
        return default


class _FirecrawlConfig:
    """Config that forces the Firecrawl backend."""

    def get(self, key, default=None):
        if key == "web_backend":
            return "Firecrawl"
        if key == "firecrawl_url":
            return "http://fc.example.test:13002"
        return default


# --- can_handle: universal fallback contract ---

def test_can_handle_accepts_any_url():
    channel = WebChannel()
    for sample in [
        "https://example.com",
        "http://example.com/path?q=1",
        "example.com",
        "ftp://files.example.com/readme.txt",
        "not a url at all",
        "",
    ]:
        assert channel.can_handle(sample) is True, sample


# --- check: honors override + probes Firecrawl ---

def test_check_ok_and_no_network_when_jina_overridden():
    import urllib.request
    channel = WebChannel()
    mock_open = MagicMock()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(urllib.request, "urlopen", mock_open)
        status, message = channel.check(_JinaConfig())
    assert status == "ok"
    assert channel.active_backend == "Jina Reader"
    assert "Jina Reader" in message
    # Jina override skips the Firecrawl probe: zero network calls.
    mock_open.assert_not_called()


def test_check_ok_when_firecrawl_reachable():
    import urllib.request
    channel = WebChannel()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(urllib.request, "urlopen", lambda req, timeout=None: _resp(b"{}"))
        status, message = channel.check(_FirecrawlConfig())
    assert status == "ok"
    assert channel.active_backend == "Firecrawl"
    assert "Firecrawl" in message


def test_check_warn_and_falls_back_to_jina_when_firecrawl_down():
    import urllib.request
    from urllib.error import URLError
    channel = WebChannel()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(urllib.request, "urlopen", _err(URLError("connection refused")))
        status, message = channel.check(_FirecrawlConfig())
    assert status == "warn"
    assert channel.active_backend == "Jina Reader"
    assert "Firecrawl 不可用" in message


def test_check_default_prefers_firecrawl_when_no_override():
    import urllib.request
    channel = WebChannel()
    # No config: default ordered backends → Firecrawl first. Probe it.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(urllib.request, "urlopen", lambda req, timeout=None: _resp(b"{}"))
        status, _ = channel.check()
    assert status == "ok"
    assert channel.active_backend == "Firecrawl"


def test_firecrawl_base_url_honors_env(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_URL", "http://my-fc:9999/")
    assert WebChannel._firecrawl_base_url() == "http://my-fc:9999"
    monkeypatch.delenv("FIRECRAWL_URL", raising=False)


def test_firecrawl_base_url_default():
    assert WebChannel._firecrawl_base_url() == _DEFAULT_FIRECRAWL_URL


# --- read: Jina path (forced via override) — URL normalisation + request shape ---

def test_read_jina_prepends_https_for_schemeless_url(monkeypatch):
    import urllib.request
    channel = WebChannel()
    mock_open = MagicMock(return_value=_resp())
    monkeypatch.setattr(urllib.request, "urlopen", mock_open)
    out = channel.read("example.com/article", config=_JinaConfig())
    req = mock_open.call_args.args[0]
    assert req.full_url == "https://r.jina.ai/https://example.com/article"
    assert out == "# Example\nfull text\n"


def test_read_jina_preserves_existing_http_scheme(monkeypatch):
    import urllib.request
    channel = WebChannel()
    mock_open = MagicMock(return_value=_resp())
    monkeypatch.setattr(urllib.request, "urlopen", mock_open)
    channel.read("http://example.com", config=_JinaConfig())
    req = mock_open.call_args.args[0]
    assert req.full_url == "https://r.jina.ai/http://example.com"


def test_read_jina_preserves_existing_https_scheme(monkeypatch):
    import urllib.request
    channel = WebChannel()
    mock_open = MagicMock(return_value=_resp())
    monkeypatch.setattr(urllib.request, "urlopen", mock_open)
    channel.read("https://example.com/deep/path", config=_JinaConfig())
    req = mock_open.call_args.args[0]
    assert req.full_url == "https://r.jina.ai/https://example.com/deep/path"


def test_read_jina_sends_expected_headers_and_timeout(monkeypatch):
    import urllib.request
    channel = WebChannel()
    mock_open = MagicMock(return_value=_resp())
    monkeypatch.setattr(urllib.request, "urlopen", mock_open)
    channel.read("https://example.com", config=_JinaConfig())
    req = mock_open.call_args.args[0]
    assert req.headers == {"User-agent": _UA, "Accept": "text/plain"}
    assert mock_open.call_args.kwargs["timeout"] == 30


def test_read_jina_decodes_utf8_body(monkeypatch):
    import urllib.request
    channel = WebChannel()
    monkeypatch.setattr(
        urllib.request, "urlopen",
        MagicMock(return_value=_resp("café ☕\n".encode("utf-8"))),
    )
    out = channel.read("https://example.com", config=_JinaConfig())
    assert out == "café ☕\n"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "http://localhost/admin",
        "http://intranet/admin",
        "http://home.arpa/admin",
        "http://metadata.google.internal/latest/meta-data",
        "http://127.0.0.1/private",
        "http://127.1/private",
        "http://169.254.169.254/latest/meta-data",
        "http://192.168.1/private",
        "http://0/private",
        "http://2130706433/private",
        "http://0x7f000001/private",
        "http://0177.0.0.1/private",
        "http://2852039166/latest/meta-data",
        "http://0xA9FEA9FE/latest/meta-data",
        "http://[::1]/private",
        "http://[::ffff:127.0.0.1]/private",
        "http://localhost./admin",
        "http://127.0.0.1\\example.com/private",
        "https://user:password@example.com/private",
    ],
)
def test_read_rejects_non_public_urls_before_network(url, monkeypatch):
    import urllib.request
    channel = WebChannel()
    mock_open = MagicMock()
    monkeypatch.setattr(urllib.request, "urlopen", mock_open)
    with pytest.raises(ValueError, match="public HTTP"):
        channel.read(url, config=_JinaConfig())
    mock_open.assert_not_called()


@pytest.mark.parametrize("url", ["https://8.8.8.8/page", "http://010.010.010.010/page"])
def test_read_allows_public_literal_addresses(url, monkeypatch):
    import urllib.request
    channel = WebChannel()
    mock_open = MagicMock(return_value=_resp())
    monkeypatch.setattr(urllib.request, "urlopen", mock_open)
    channel.read(url, config=_JinaConfig())
    mock_open.assert_called_once()


def test_read_jina_accepts_response_at_exact_size_limit(monkeypatch):
    import urllib.request
    channel = WebChannel()
    response = _resp(b"x" * _MAX_RESPONSE_BYTES)
    monkeypatch.setattr(urllib.request, "urlopen", MagicMock(return_value=response))
    out = channel.read("https://example.com/exact", config=_JinaConfig())
    assert len(out) == _MAX_RESPONSE_BYTES
    response.__enter__.return_value.read.assert_called_once_with(_MAX_RESPONSE_BYTES + 1)


def test_read_jina_rejects_oversized_reader_response(monkeypatch):
    import urllib.request
    channel = WebChannel()
    response = _resp(b"x" * (_MAX_RESPONSE_BYTES + 1))
    monkeypatch.setattr(urllib.request, "urlopen", MagicMock(return_value=response))
    with pytest.raises(ValueError, match="response exceeds"):
        channel.read("https://example.com/large", config=_JinaConfig())
    response.__enter__.return_value.read.assert_called_once_with(_MAX_RESPONSE_BYTES + 1)


@pytest.mark.parametrize(
    "body",
    [
        (
            "Title: Just a moment...\n\n"
            "URL Source: https://imginn.com/instagram/\n\n"
            "Warning: This page maybe requiring CAPTCHA\n\n"
            "Markdown Content:\n\n"
            "## Performing security verification\n"
        ),
        (
            "Title: Attention Required! | Cloudflare\n\n"
            "Sorry, you have been blocked.\n\nRay ID: 1234567890abcdef\n"
        ),
    ],
)
def test_read_jina_rejects_high_confidence_antibot_pages(body, monkeypatch):
    import urllib.request
    channel = WebChannel()
    mock_open = MagicMock(return_value=_resp(body.encode("utf-8")))
    monkeypatch.setattr(urllib.request, "urlopen", mock_open)
    with pytest.raises(RuntimeError, match="反爬验证页"):
        channel.read("https://example.com/protected", config=_JinaConfig())
    mock_open.assert_called_once()


@pytest.mark.parametrize(
    "body",
    [
        "# A guide to security verification\n",
        "# DDoS protection explained\n",
        "# Checking your browser automation\n",
        "# Please turn JavaScript on for progressive enhancement\n",
        "# A history of cf-browser-verify\n",
        "Title: Just a moment...\n\nA short-story review.\n",
    ],
)
def test_read_jina_does_not_reject_single_generic_antibot_terms(body, monkeypatch):
    import urllib.request
    channel = WebChannel()
    monkeypatch.setattr(
        urllib.request, "urlopen",
        MagicMock(return_value=_resp(body.encode("utf-8"))),
    )
    assert channel.read("https://example.com/article", config=_JinaConfig()) == body


def test_antibot_detection_has_a_fixed_scan_window(monkeypatch):
    import urllib.request
    channel = WebChannel()
    body = (
        "x" * 4096
        + "Warning: requiring CAPTCHA\n"
        + "Title: Just a moment...\n"
        + "## Performing security verification\n"
    )
    monkeypatch.setattr(
        urllib.request, "urlopen",
        MagicMock(return_value=_resp(body.encode("utf-8"))),
    )
    assert channel.read("https://example.com/long-article", config=_JinaConfig()) == body


# --- read: Firecrawl path ---

def _firecrawl_ok(markdown="# hi\n"):
    """A successful Firecrawl v1/scrape JSON payload."""
    import json
    return json.dumps(
        {"success": True, "data": {"markdown": markdown}}
    ).encode("utf-8")


def test_read_firecrawl_returns_markdown(monkeypatch):
    import urllib.request
    channel = WebChannel()
    mock_open = MagicMock(return_value=_resp(_firecrawl_ok("# body\n")))
    monkeypatch.setattr(urllib.request, "urlopen", mock_open)
    out = channel.read("https://example.com", config=_FirecrawlConfig())
    assert out == "# body\n"
    req = mock_open.call_args.args[0]
    assert req.full_url == "http://fc.example.test:13002/v1/scrape"
    assert req.get_method() == "POST"
    assert req.headers.get("Content-type") == "application/json"
    assert "Jina" not in req.full_url  # did not fall through


def test_read_firecrawl_sends_bearer_when_api_key_set(monkeypatch):
    import urllib.request
    channel = WebChannel()

    class _Cfg:
        def get(self, key, default=None):
            if key == "web_backend":
                return "Firecrawl"
            if key == "firecrawl_url":
                return "http://fc.example.test:13002"
            if key == "firecrawl_api_key":
                return "secret-key"
            return default

    mock_open = MagicMock(return_value=_resp(_firecrawl_ok())
)
    monkeypatch.setattr(urllib.request, "urlopen", mock_open)
    channel.read("https://example.com", config=_Cfg())
    req = mock_open.call_args.args[0]
    assert req.headers.get("Authorization") == "Bearer secret-key"


def test_read_firecrawl_scrape_error_propagates_not_fallback(monkeypatch):
    """success:false is a content failure — must propagate, NOT fall to Jina."""
    import urllib.request
    channel = WebChannel()
    payload = b'{"success": false, "error": "timeout"}'
    mock_open = MagicMock(return_value=_resp(payload))
    monkeypatch.setattr(urllib.request, "urlopen", mock_open)
    with pytest.raises(RuntimeError, match="Firecrawl 抓取失败"):
        channel.read("https://example.com", config=_FirecrawlConfig())
    mock_open.assert_called_once()  # no Jina attempt


def test_read_firecrawl_oversize_propagates_not_fallback(monkeypatch):
    import urllib.request
    channel = WebChannel()
    payload = b"x" * (_MAX_RESPONSE_BYTES + 1)
    mock_open = MagicMock(return_value=_resp(payload))
    monkeypatch.setattr(urllib.request, "urlopen", mock_open)
    with pytest.raises(ValueError, match="response exceeds"):
        channel.read("https://example.com/large", config=_FirecrawlConfig())
    mock_open.assert_called_once()


def test_read_firecrawl_bad_json_propagates_not_fallback(monkeypatch):
    import urllib.request
    channel = WebChannel()
    mock_open = MagicMock(return_value=_resp(b"not json"))
    monkeypatch.setattr(urllib.request, "urlopen", mock_open)
    with pytest.raises(RuntimeError, match="不是有效 JSON"):
        channel.read("https://example.com", config=_FirecrawlConfig())
    mock_open.assert_called_once()


# --- read: fallback semantics — transport failure falls through to Jina ---

def test_read_falls_back_to_jina_on_firecrawl_network_error(monkeypatch):
    """Firecrawl unreachable (transport) → Jina used; Jina result returned."""
    import urllib.request
    from urllib.error import URLError
    channel = WebChannel()
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)
        if "/v1/scrape" in req.full_url:
            raise URLError("connection refused")
        return _resp(b"# via jina\n")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    out = channel.read("https://example.com", config=_FirecrawlConfig())
    assert out == "# via jina\n"
    assert len(calls) == 2
    assert "r.jina.ai" in calls[1]


def test_read_falls_back_on_firecrawl_timeout(monkeypatch):
    import urllib.request
    import socket
    channel = WebChannel()
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)
        if "/v1/scrape" in req.full_url:
            raise socket.timeout("timed out")
        return _resp(b"# jina\n")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    out = channel.read("https://example.com", config=_FirecrawlConfig())
    assert out == "# jina\n"


def test_read_all_backends_down_raises_last_network_error(monkeypatch):
    import urllib.request
    from urllib.error import URLError
    channel = WebChannel()
    mock_open = MagicMock(side_effect=URLError("down"))
    monkeypatch.setattr(urllib.request, "urlopen", mock_open)
    with pytest.raises(URLError):
        channel.read("https://example.com", config=_FirecrawlConfig())
    assert mock_open.call_count == 2  # tried Firecrawl then Jina


def test_read_normalizes_url_before_firecrawl_call(monkeypatch):
    import urllib.request
    channel = WebChannel()
    captured = []

    def fake_urlopen(req, timeout=None):
        captured.append(req.data)
        return _resp(_firecrawl_ok())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    channel.read("example.com/article", config=_FirecrawlConfig())
    import json
    body = json.loads(captured[0])
    assert body["url"] == "https://example.com/article"


def test_read_rejects_non_public_url_before_firecrawl(monkeypatch):
    import urllib.request
    channel = WebChannel()
    mock_open = MagicMock()
    monkeypatch.setattr(urllib.request, "urlopen", mock_open)
    with pytest.raises(ValueError, match="public HTTP"):
        channel.read("http://localhost/admin", config=_FirecrawlConfig())
    mock_open.assert_not_called()
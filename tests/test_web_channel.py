# -*- coding: utf-8 -*-
"""Dedicated tests for the ``web`` channel.

``web`` is the tier-0 catch-all: ``can_handle`` must accept *anything* so it
can back-stop every other channel, ``check`` must report ready without touching
the network (it is the zero-overhead fallback), and ``read`` must normalise the
URL before handing it to Jina Reader. Follow-up to #331 / #360 / #361,
completing dedicated coverage for the channels that still lacked it.
"""

import http.client
import json
from unittest.mock import MagicMock, patch

import pytest

from agent_reach.channels.web import _UA, WebChannel
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import BAD_INPUT, RATE_LIMITED, UPSTREAM_BROKEN

_MAX_RESPONSE_BYTES = 5 * 1024 * 1024


def test_search_does_not_turn_unrecognized_payload_into_empty_success():
    from agent_reach.runtime.result import ReachError

    with patch("agent_reach.channels.web._exa_call", return_value="Service temporarily unavailable"):
        with pytest.raises(ReachError, match="no recognizable search results"):
            WebChannel()._exa_search(query="python", limit=3, timeout=5)


def test_exa_request_identifies_agent_reach_not_python_urllib():
    # Exa's Cloudflare returns 403 (error 1010) for the default Python-urllib agent.
    from agent_reach.channels.web import _exa_call
    body = json.dumps({"result": {"content": [{"type": "text", "text": "Content"}]}}).encode()
    resp = MagicMock()
    resp.__enter__.return_value = resp
    resp.read.return_value = body
    resp.headers = {}
    with patch("agent_reach.runtime.run.urllib.request.urlopen", return_value=resp) as urlopen:
        _exa_call("web_search_exa", {"query": "q"}, 5)
    assert urlopen.call_args.args[0].get_header("User-agent").startswith("agent-reach/")


def test_exa_retries_a_truncated_read_once_within_the_same_budget():
    from agent_reach.channels.web import _exa_call
    body = json.dumps({"result": {"content": [{"type": "text", "text": "Content"}]}}).encode()
    with patch("agent_reach.channels.web.http_request", side_effect=[http.client.IncompleteRead(b""), body]) as request:
        assert _exa_call("web_fetch_exa", {"urls": ["https://example.com"]}, 5) == "Content"
    assert request.call_count == 2
    assert 0 < request.call_args_list[1].kwargs["timeout"] <= request.call_args_list[0].kwargs["timeout"] <= 5


def test_exa_never_loops_after_two_truncated_reads():
    from agent_reach.channels.web import _exa_call
    with patch("agent_reach.channels.web.http_request", side_effect=http.client.IncompleteRead(b"")) as request:
        with pytest.raises(http.client.IncompleteRead):
            _exa_call("web_fetch_exa", {"urls": ["https://example.com"]}, 5)
    assert request.call_count == 2


def test_exa_does_not_retry_http_limits_or_access_denials():
    import urllib.error

    from agent_reach.channels.web import _exa_call
    for code in (429, 403):
        with patch("agent_reach.channels.web.http_request", side_effect=urllib.error.HTTPError("https://mcp.exa.ai/mcp", code, "denied", {}, None)) as request:
            with pytest.raises(urllib.error.HTTPError):
                _exa_call("web_fetch_exa", {"urls": ["https://example.com"]}, 5)
        request.assert_called_once()


@pytest.mark.parametrize(
    "message",
    [
        "Request failed with status code 429",
        "You have reached the free hosted Exa MCP rate limit",
        "Monthly quota exceeded",
        "Your account has insufficient credits",
        "Free usage limit reached",
    ],
)
@pytest.mark.parametrize("rpc_error", [False, True])
def test_exa_hosted_limits_stop_as_rate_limited(message, rpc_error):
    payload = {"error": {"message": message}} if rpc_error else {
        "result": {"isError": True, "content": [{"type": "text", "text": message}]},
    }
    with patch("agent_reach.channels.web.http_request", return_value=json.dumps(payload).encode()) as request:
        out = run_action(WebChannel(), "search", {"query": "python"})
    assert out["error"]["code"] == RATE_LIMITED
    assert "built-in web search" in out["error"]["hint"]
    request.assert_called_once()


def test_exa_invalid_rpc_params_are_bad_input():
    payload = {"error": {"code": -32602, "message": "Invalid params: missing query"}}
    with patch("agent_reach.channels.web.http_request", return_value=json.dumps(payload).encode()):
        out = run_action(WebChannel(), "search", {"query": "python"})
    assert out["error"]["code"] == BAD_INPUT


def test_exa_generic_failure_and_result_size_error_are_not_rate_limits():
    for message in ("Service temporarily unavailable", "Invalid result limit: expected a number"):
        payload = {"result": {"isError": True, "content": [{"type": "text", "text": message}]}}
        with patch("agent_reach.channels.web.http_request", return_value=json.dumps(payload).encode()):
            out = run_action(WebChannel(), "search", {"query": "python"})
        assert out["error"]["code"] == UPSTREAM_BROKEN


def test_web_missing_query_is_rejected_without_calling_exa():
    with patch("agent_reach.channels.web.http_request") as request:
        out = run_action(WebChannel(), "search", {})
    assert out["error"]["code"] == BAD_INPUT
    request.assert_not_called()


def _resp(body=b"# Example\nfull text\n"):
    """A urlopen() return value usable as a context manager."""
    cm = MagicMock()
    cm.__enter__.return_value.read.return_value = body
    return cm


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


# --- check: ready without any network probe (零开销兜底) ---



# --- read: URL normalisation + Jina Reader request shape ---

def test_read_prepends_https_for_schemeless_url():
    channel = WebChannel()
    with patch("urllib.request.urlopen", return_value=_resp()) as mock_open:
        out = channel.read("example.com/article")
    req = mock_open.call_args.args[0]
    assert req.full_url == "https://r.jina.ai/https://example.com/article"
    assert out == "# Example\nfull text\n"


def test_read_preserves_existing_http_scheme():
    channel = WebChannel()
    with patch("urllib.request.urlopen", return_value=_resp()) as mock_open:
        channel.read("http://example.com")
    req = mock_open.call_args.args[0]
    # http:// must be kept as-is, not coerced to https:// nor double-prefixed.
    assert req.full_url == "https://r.jina.ai/http://example.com"


def test_read_preserves_existing_https_scheme():
    channel = WebChannel()
    with patch("urllib.request.urlopen", return_value=_resp()) as mock_open:
        channel.read("https://example.com/deep/path")
    req = mock_open.call_args.args[0]
    assert req.full_url == "https://r.jina.ai/https://example.com/deep/path"


def test_read_sends_expected_headers_and_timeout():
    channel = WebChannel()
    with patch("urllib.request.urlopen", return_value=_resp()) as mock_open:
        channel.read("https://example.com")
    req = mock_open.call_args.args[0]
    assert req.headers == {"User-agent": _UA, "Accept": "text/plain"}
    assert mock_open.call_args.kwargs["timeout"] == 30


def test_read_decodes_utf8_body():
    channel = WebChannel()
    with patch("urllib.request.urlopen", return_value=_resp("café ☕\n".encode("utf-8"))):
        out = channel.read("https://example.com")
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
def test_read_rejects_non_public_urls_before_network(url):
    channel = WebChannel()

    with patch("urllib.request.urlopen") as mock_open:
        with pytest.raises(ValueError, match="public HTTP"):
            channel.read(url)

    mock_open.assert_not_called()


@pytest.mark.parametrize("url", ["https://8.8.8.8/page", "http://010.010.010.010/page"])
def test_read_allows_public_literal_addresses(url):
    channel = WebChannel()
    with patch("urllib.request.urlopen", return_value=_resp()) as mock_open:
        channel.read(url)
    mock_open.assert_called_once()


def test_read_accepts_response_at_exact_size_limit():
    channel = WebChannel()
    response = _resp(b"x" * _MAX_RESPONSE_BYTES)

    with patch("urllib.request.urlopen", return_value=response):
        out = channel.read("https://example.com/exact")

    assert len(out) == _MAX_RESPONSE_BYTES
    response.__enter__.return_value.read.assert_called_once_with(
        _MAX_RESPONSE_BYTES + 1
    )


def test_read_rejects_oversized_reader_response():
    channel = WebChannel()
    response = _resp(b"x" * (_MAX_RESPONSE_BYTES + 1))

    with patch("urllib.request.urlopen", return_value=response):
        with pytest.raises(ValueError, match="response exceeds"):
            channel.read("https://example.com/large")

    response.__enter__.return_value.read.assert_called_once_with(
        _MAX_RESPONSE_BYTES + 1
    )


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
def test_read_rejects_high_confidence_antibot_pages(body):
    channel = WebChannel()

    with patch(
        "urllib.request.urlopen", return_value=_resp(body.encode("utf-8"))
    ) as mock_open:
        with pytest.raises(RuntimeError, match="反爬验证页"):
            channel.read("https://example.com/protected")

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
def test_read_does_not_reject_single_generic_antibot_terms(body):
    channel = WebChannel()

    with patch("urllib.request.urlopen", return_value=_resp(body.encode("utf-8"))):
        assert channel.read("https://example.com/article") == body


def test_antibot_detection_has_a_fixed_scan_window():
    channel = WebChannel()
    body = (
        "x" * 4096
        + "Warning: requiring CAPTCHA\n"
        + "Title: Just a moment...\n"
        + "## Performing security verification\n"
    )

    with patch("urllib.request.urlopen", return_value=_resp(body.encode("utf-8"))):
        assert channel.read("https://example.com/long-article") == body

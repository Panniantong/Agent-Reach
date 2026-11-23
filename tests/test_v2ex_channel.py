# -*- coding: utf-8 -*-
"""Dedicated tests for the ``v2ex`` channel.

V2EX rides the public JSON API and reshapes each endpoint: hot/node topic
lists, a single-topic view that must tolerate the list-or-dict response
shape and a failing replies fetch, a user profile with avatar/url
fallbacks, and a search method that is intentionally offline (the public
API has no search endpoint). These tests stub the shared ``_get_json`` so
the shaping logic runs offline. Follow-up to #331 — extends dedicated
channel coverage after rss (#360), github (#361), web (#363),
reddit (#364) and xueqiu (#365).
"""

import json
import ssl
import subprocess
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from agent_reach.channels import v2ex as v2
from agent_reach.channels.v2ex import V2EXChannel
from agent_reach.runtime.dispatch import run_action

# --- can_handle ---

def test_can_handle_matches_v2ex_hosts():
    ch = V2EXChannel()
    for url in ["https://www.v2ex.com/t/123", "https://V2EX.COM/go/python"]:
        assert ch.can_handle(url) is True, url
    for url in ["https://example.com", "https://twitter.com", ""]:
        assert ch.can_handle(url) is False, url


# --- check() ---





def test_get_json_retries_unexpected_tls_eof_with_bounded_curl():
    payload = [{"id": 1}]
    tls_error = URLError(
        ssl.SSLError(
            "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol"
        )
    )

    with patch.object(v2, "_get_json_with_urllib", side_effect=tls_error), patch.object(
        v2.shutil, "which", return_value="C:/Windows/System32/curl.exe"
    ), patch.object(
        v2.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            ["curl"], 0, json.dumps(payload), ""
        ),
    ) as run:
        assert v2._get_json("https://www.v2ex.com/api/topics/hot.json") == payload

    command = run.call_args.args[0]
    assert command[0] == "C:/Windows/System32/curl.exe"
    assert "--fail" in command
    assert command[command.index("--proto") + 1] == "=https"
    assert "--location" not in command
    assert "--max-time" in command
    assert "--max-filesize" in command
    assert command[-2:] == [
        "--url",
        "https://www.v2ex.com/api/topics/hot.json",
    ]
    assert run.call_args.kwargs["timeout"] == v2._TIMEOUT + 2


def test_get_json_does_not_hide_certificate_verification_failures():
    certificate_error = ssl.SSLCertVerificationError(
        "certificate verify failed"
    )

    with patch.object(
        v2, "_get_json_with_urllib", side_effect=certificate_error
    ), patch.object(v2.subprocess, "run") as run:
        with pytest.raises(ssl.SSLCertVerificationError):
            v2._get_json("https://www.v2ex.com/api/topics/hot.json")

    run.assert_not_called()


def test_get_json_does_not_fallback_for_plain_error_text():
    fake_error = RuntimeError(
        "UNEXPECTED_EOF_WHILE_READING appeared in an unrelated message"
    )

    with patch.object(
        v2, "_get_json_with_urllib", side_effect=fake_error
    ), patch.object(v2.subprocess, "run") as run:
        with pytest.raises(RuntimeError, match="unrelated"):
            v2._get_json("https://www.v2ex.com/api/topics/hot.json")

    run.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "http://www.v2ex.com/api/topics/hot.json",
        "https://v2ex.com.evil.test/api/topics/hot.json",
        "https://user:pass@www.v2ex.com/api/topics/hot.json",
        "https://www.v2ex.com:8443/api/topics/hot.json",
        "https://www.v2ex.com/about",
    ],
)
def test_get_json_rejects_non_api_targets_before_network(url):
    with patch.object(v2.urllib.request, "urlopen") as urlopen, patch.object(
        v2.subprocess, "run"
    ) as run:
        with pytest.raises(ValueError, match="V2EX HTTPS API"):
            v2._get_json(url)

    urlopen.assert_not_called()
    run.assert_not_called()




# --- get_hot_topics / get_node_topics ---









# --- get_topic: list-or-dict shape + replies fetch + fallbacks ---









# --- get_user: field mapping + avatar/url fallbacks ---









# --- search: intentionally offline (no public search endpoint) ---





@pytest.mark.parametrize(
    "error",
    [TimeoutError("TLS handshake timed out"), URLError(TimeoutError("TLS handshake timed out"))],
    ids=["direct-timeout", "urlerror-timeout"],
)
def test_hot_recovers_from_urllib_timeout_with_curl(error):
    payload = [{"id": 1, "title": "Recovered topic", "url": "https://www.v2ex.com/t/1"}]
    with patch.object(v2.urllib.request, "urlopen", side_effect=error), patch.object(
        v2.shutil, "which", return_value="/usr/bin/curl"
    ), patch.object(
        v2.subprocess, "run",
        return_value=subprocess.CompletedProcess(["curl"], 0, json.dumps(payload), ""),
    ) as curl:
        result = run_action(V2EXChannel(), "hot", {"limit": 1})

    assert result["ok"] is True
    assert result["backend"] == "v2ex-api"
    assert result["items"][0]["title"] == "Recovered topic"
    assert result["items"][0]["url"] == "https://www.v2ex.com/t/1"
    curl.assert_called_once()
    command = curl.call_args.args[0]
    assert command[command.index("--max-time") + 1] == str(v2._TIMEOUT)
    assert command[command.index("--proto") + 1] == "=https"
    assert "--insecure" not in command
    assert "--location" not in command


@pytest.mark.parametrize(
    "error",
    [
        ssl.SSLCertVerificationError("certificate verify failed"),
        URLError(ssl.SSLCertVerificationError("certificate verify failed")),
        HTTPError("https://www.v2ex.com/api/topics/hot.json", 429, "Too Many Requests", None, None),
        URLError("TLS handshake timed out"),
        ValueError("invalid JSON response"),
    ],
    ids=["certificate", "wrapped-certificate", "http-error", "timeout-text", "invalid-json"],
)
def test_hot_does_not_retry_unrelated_or_certificate_errors(error):
    with patch.object(v2.urllib.request, "urlopen", side_effect=error), patch.object(
        v2.subprocess, "run"
    ) as curl:
        result = run_action(V2EXChannel(), "hot", {"limit": 1})

    assert result["ok"] is False
    curl.assert_not_called()

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
from urllib.error import URLError

import pytest

from agent_reach.channels import v2ex as v2
from agent_reach.channels.v2ex import V2EXChannel

# --- can_handle ---

def test_can_handle_matches_v2ex_hosts():
    ch = V2EXChannel()
    for url in ["https://www.v2ex.com/t/123", "https://V2EX.COM/go/python"]:
        assert ch.can_handle(url) is True, url
    for url in ["https://example.com", "https://twitter.com", ""]:
        assert ch.can_handle(url) is False, url


# --- check() ---

def test_check_ok_sets_active_backend():
    ch = V2EXChannel()
    with patch.object(v2, "_get_json", return_value=[{"id": 1}]):
        status, message = ch.check()
    assert status == "ok"
    assert ch.active_backend == ch.backends[0]


def test_check_warn_on_exception_clears_backend():
    ch = V2EXChannel()
    ch.active_backend = "stale"
    with patch.object(v2, "_get_json", side_effect=OSError("no proxy")):
        status, message = ch.check()
    assert status == "warn"
    assert "连接失败" in message
    assert ch.active_backend is None


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


def test_check_is_healthy_when_native_curl_recovers_tls_eof():
    ch = V2EXChannel()
    tls_error = ssl.SSLError(
        "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol"
    )

    with patch.object(v2, "_get_json_with_urllib", side_effect=tls_error), patch.object(
        v2.shutil, "which", return_value="/usr/bin/curl"
    ), patch.object(
        v2.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(["curl"], 0, "[]", ""),
    ):
        status, _message = ch.check()

    assert status == "ok"
    assert ch.active_backend == ch.backends[0]


# --- get_hot_topics / get_node_topics ---

def test_get_hot_topics_maps_node_and_truncates_content():
    ch = V2EXChannel()
    items = [{
        "id": 9, "title": "T", "url": "https://www.v2ex.com/t/9",
        "replies": 12, "content": "x" * 300,
        "node": {"name": "python", "title": "Python"},
    }]
    with patch.object(v2, "_get_json", return_value=items):
        topics = ch.get_hot_topics(limit=5)
    t = topics[0]
    assert t["node_name"] == "python"
    assert t["node_title"] == "Python"
    assert len(t["content"]) == 200
    assert t["replies"] == 12


def test_get_hot_topics_respects_limit():
    ch = V2EXChannel()
    items = [{"id": i} for i in range(10)]
    with patch.object(v2, "_get_json", return_value=items):
        assert len(ch.get_hot_topics(limit=3)) == 3


def test_get_node_topics_falls_back_to_requested_node_name():
    ch = V2EXChannel()
    # node missing in the payload -> node_name falls back to the requested one
    with patch.object(v2, "_get_json", return_value=[{"id": 1, "title": "x"}]):
        topics = ch.get_node_topics("jobs")
    assert topics[0]["node_name"] == "jobs"


# --- get_topic: list-or-dict shape + replies fetch + fallbacks ---

def test_get_topic_unwraps_list_and_maps_replies():
    ch = V2EXChannel()
    topic = [{
        "id": 42, "title": "Hello", "url": "https://www.v2ex.com/t/42",
        "content": "body", "replies": 2,
        "node": {"name": "tech", "title": "Tech"},
        "member": {"username": "op"},
    }]
    replies = [
        {"member": {"username": "alice"}, "content": "nice", "created": 1},
        {"member": {"username": "bob"}, "content": "+1", "created": 2},
    ]
    with patch.object(v2, "_get_json", side_effect=[topic, replies]):
        result = ch.get_topic(42)
    assert result["id"] == 42
    assert result["author"] == "op"
    assert result["node_name"] == "tech"
    assert len(result["replies"]) == 2
    assert result["replies"][0] == {"author": "alice", "content": "nice", "created": 1}


def test_get_topic_survives_failing_replies_fetch():
    ch = V2EXChannel()
    topic = {"id": 7, "title": "x"}  # dict shape (not a list)
    with patch.object(v2, "_get_json", side_effect=[topic, OSError("boom")]):
        result = ch.get_topic(7)
    assert result["id"] == 7
    assert result["replies"] == []  # failed replies fetch degrades to empty


def test_get_topic_url_fallback_when_missing():
    ch = V2EXChannel()
    with patch.object(v2, "_get_json", side_effect=[[], []]):
        result = ch.get_topic(99)
    assert result["id"] == 99
    assert result["url"] == "https://www.v2ex.com/t/99"


# --- get_user: field mapping + avatar/url fallbacks ---

def test_get_user_maps_fields_and_prefers_large_avatar():
    ch = V2EXChannel()
    data = {
        "id": 1, "username": "neo", "github": "neo-gh",
        "avatar_large": "/large.png", "avatar_normal": "/normal.png",
    }
    with patch.object(v2, "_get_json", return_value=data):
        user = ch.get_user("neo")
    assert user["github"] == "neo-gh"
    assert user["avatar"] == "/large.png"


def test_get_user_avatar_falls_back_to_normal():
    ch = V2EXChannel()
    with patch.object(v2, "_get_json", return_value={"avatar_normal": "/normal.png"}):
        user = ch.get_user("neo")
    assert user["avatar"] == "/normal.png"
    # url + username fall back to the requested handle
    assert user["username"] == "neo"
    assert user["url"] == "https://www.v2ex.com/member/neo"


# --- search: intentionally offline (no public search endpoint) ---

def test_search_returns_guidance_without_network():
    ch = V2EXChannel()
    with patch.object(v2, "_get_json", side_effect=AssertionError("must not hit network")):
        results = ch.search("python")
    assert len(results) == 1
    assert "error" in results[0]
    assert "python" in results[0]["error"]

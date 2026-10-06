# -*- coding: utf-8 -*-
"""Dedicated tests for the ``mastodon`` channel.

Mastodon rides the public per-instance JSON API: account lookup on the
account's HOME instance, paginated statuses, single-status fetch (remote
"/@user@instance/<id>" URLs resolve to the remote home instance), and a
federated account search that needs an optional MASTODON_TOKEN and degrades
to exact-handle lookup without one. ``can_handle`` is a pure instance-domain
allowlist (no bare "/@user" path matching — YouTube/Medium use that shape).
These tests stub the shared ``_get_json`` so the shaping logic runs offline.
"""

import json
import os
import ssl
import subprocess
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from agent_reach.channels import mastodon as m
from agent_reach.channels.mastodon import MastodonChannel


def _account(acct="kate", **kw):
    data = {
        "id": "7",
        "acct": acct,
        "display_name": "Kate Starbird",
        "url": f"https://mstdn.social/@{acct}",
        "note": "<p>prof at <b>uw</b></p>",
        "followers_count": 100,
        "following_count": 50,
        "statuses_count": 999,
        "created_at": "2020-01-02T03:04:05.000Z",
        "avatar": "https://mstdn.social/a.png",
    }
    data.update(kw)
    return data


def _status(sid="1", acct="kate", content="hello", **kw):
    data = {
        "id": sid,
        "created_at": "2026-01-02T10:00:00.000Z",
        "url": f"https://mstdn.social/@{acct}/{sid}",
        "content": f"<p>{content}</p>",
        "account": {"id": "7", "acct": acct, "display_name": "Kate"},
        "favourites_count": 1,
        "reblogs_count": 2,
        "replies_count": 3,
    }
    data.update(kw)
    return data


# --- can_handle ---

def test_can_handle_matches_known_instances():
    ch = MastodonChannel()
    for url in [
        "https://mastodon.social/@Gargron",
        "https://mstdn.social/@kate/123",
        "https://FOSSTODON.ORG/@dev",
    ]:
        assert ch.can_handle(url) is True, url


def test_can_handle_rejects_other_platforms_and_lookalikes():
    ch = MastodonChannel()
    for url in [
        "https://youtube.com/@handle",  # same "/@user" shape — must NOT match
        "https://medium.com/@handle",
        "https://mastodon.social.evil.test/@user",
        "https://example.com/@user",
        "https://universeodon.com/@user",  # fediverse but not whitelisted: use handle form
        "",
    ]:
        assert ch.can_handle(url) is False, url


# --- parse_handle ---

def test_parse_handle_accepts_handle_forms():
    assert m.parse_handle("@kate@mstdn.social") == ("kate", "mstdn.social")
    assert m.parse_handle("kate@mstdn.social") == ("kate", "mstdn.social")
    assert m.parse_handle("@user@hci-social.org") == ("user", "hci-social.org")


def test_parse_handle_accepts_profile_urls_with_trailing_slash():
    # regression: profile URLs ending in "/" must resolve
    assert m.parse_handle("https://mstdn.social/@kate/") == ("kate", "mstdn.social")
    assert m.parse_handle("https://mstdn.social/@kate") == ("kate", "mstdn.social")
    assert m.parse_handle("https://mstdn.social/@kate/123") == ("kate", "mstdn.social")


def test_parse_handle_url_with_remote_account_resolves_to_remote_instance():
    # account resolution: the remote part of the URL is the account's home instance
    assert m.parse_handle("https://mastodon.social/@kate@mstdn.social/42") == (
        "kate",
        "mstdn.social",
    )


@pytest.mark.parametrize(
    "bad", ["", "not-a-handle", "@justname", "user@", "@@", "https://inst/@user extra"]
)
def test_parse_handle_rejects_garbage(bad):
    with pytest.raises(ValueError, match="handle"):
        m.parse_handle(bad)


# --- check() ---

def test_check_ok_sets_active_backend():
    ch = MastodonChannel()
    with patch.object(m, "_get_json", return_value={}) as fake:
        status, message = ch.check(config={})
    assert status == "ok"
    assert "公开 API 可用" in message
    assert ch.active_backend == ch.backends[0]
    assert "/api/v1/instance" in fake.call_args.args[0]


def test_check_ok_without_token_mentions_optional_search():
    ch = MastodonChannel()
    with patch.object(m, "_get_json", return_value={}):
        _status_txt, message = ch.check(config={})
    assert "MASTODON_TOKEN" in message


def test_check_ok_with_token_reports_federated_search():
    ch = MastodonChannel()
    with patch.object(m, "_get_json", return_value={}):
        _status_txt, message = ch.check(config={"mastodon_token": "tok"})
    assert "联邦账号搜索可用" in message


def test_check_warn_on_exception_clears_backend():
    ch = MastodonChannel()
    ch.active_backend = "stale"
    with patch.object(m, "_get_json", side_effect=OSError("no proxy")):
        status, message = ch.check(config={})
    assert status == "warn"
    assert "连接失败" in message
    assert ch.active_backend is None


# --- _get_json: URL validation before network + TLS fallback ---

@pytest.mark.parametrize(
    "url",
    [
        "http://mastodon.social/api/v1/instance",
        "ftp://mastodon.social/api/v1/instance",
        "https://user:pass@mastodon.social/api/v1/instance",
        "https://mastodon.social:8443/api/v1/instance",
        "https://localhost/api/v1/instance",
        "https://127.0.0.1/api/v1/instance",
        "https://10.0.0.5/api/v1/instance",
        "https://[::1]/api/v1/instance",
        "https://mastodon.social/about",
    ],
)
def test_get_json_rejects_bad_targets_before_network(url):
    with patch.object(m.urllib.request, "urlopen") as urlopen, patch.object(
        m.subprocess, "run"
    ) as run:
        with pytest.raises(ValueError, match="Mastodon"):
            m._get_json(url)

    urlopen.assert_not_called()
    run.assert_not_called()


def test_get_json_retries_unexpected_tls_eof_with_bounded_curl():
    payload = {"domain": "mastodon.social"}
    tls_error = URLError(
        ssl.SSLError(
            "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol"
        )
    )

    with patch.object(m, "_get_json_with_urllib", side_effect=tls_error), patch.object(
        m.shutil, "which", return_value="/usr/bin/curl"
    ), patch.object(
        m.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(["curl"], 0, json.dumps(payload), ""),
    ) as run:
        assert m._get_json("https://mastodon.social/api/v1/instance", "tok") == payload

    command = run.call_args.args[0]
    assert command[0] == "/usr/bin/curl"
    assert "--fail" in command
    assert command[command.index("--proto") + 1] == "=https"
    assert "--location" not in command
    assert "--max-time" in command
    assert "--max-filesize" in command
    assert command[command.index("--header") + 1] == f"User-Agent: {m._UA}"
    token_header = command[command.index("Authorization: Bearer tok") - 1]
    assert token_header == "--header"
    assert command[-2:] == ["--url", "https://mastodon.social/api/v1/instance"]
    assert run.call_args.kwargs["timeout"] == m._TIMEOUT + 2


def test_get_json_does_not_hide_certificate_verification_failures():
    certificate_error = ssl.SSLCertVerificationError("certificate verify failed")

    with patch.object(
        m, "_get_json_with_urllib", side_effect=certificate_error
    ), patch.object(m.subprocess, "run") as run:
        with pytest.raises(ssl.SSLCertVerificationError):
            m._get_json("https://mastodon.social/api/v1/instance")

    run.assert_not_called()


def test_check_is_healthy_when_native_curl_recovers_tls_eof():
    ch = MastodonChannel()
    tls_error = ssl.SSLError(
        "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol"
    )

    with patch.object(m, "_get_json_with_urllib", side_effect=tls_error), patch.object(
        m.shutil, "which", return_value="/usr/bin/curl"
    ), patch.object(
        m.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(["curl"], 0, "{}", ""),
    ):
        status, _message = ch.check(config={})

    assert status == "ok"
    assert ch.active_backend == ch.backends[0]


# --- lookup_account ---

def test_lookup_account_maps_fields_and_appends_instance_to_local_acct():
    ch = MastodonChannel()
    captured = {}

    def fake_get_json(url, token=""):
        captured["url"] = url
        captured["token"] = token
        return _account()

    with patch.object(m, "_get_json", side_effect=fake_get_json):
        account = ch.lookup_account("@kate@mstdn.social", config={})

    parts = urlsplit(captured["url"])
    assert parts.hostname == "mstdn.social"
    assert parts.path == "/api/v1/accounts/lookup"
    assert parse_qs(parts.query)["acct"] == ["kate@mstdn.social"]
    assert captured["token"] == ""

    assert account["id"] == "7"
    assert account["handle"] == "kate@mstdn.social"
    assert account["display_name"] == "Kate Starbird"
    assert account["bio"] == "prof at uw"
    assert account["followers"] == 100
    assert account["created"] == "2020-01-02"
    assert account["instance"] == "mstdn.social"


def test_lookup_account_keeps_remote_acct_untouched():
    ch = MastodonChannel()
    with patch.object(m, "_get_json", return_value=_account(acct="kate@uw.edu")):
        account = ch.lookup_account("@kate@mstdn.social", config={})
    assert account["handle"] == "kate@uw.edu"


def test_non_search_calls_never_send_token():
    # The token must only ever be sent by search() to its (issuing) instance —
    # lookup/statuses/status/check go out credential-free.
    ch = MastodonChannel()
    tokens = []

    def fake_get_json(url, token=""):
        tokens.append(token)
        if len(tokens) <= 2:  # lookup_account + get_statuses' internal lookup
            return _account()
        if len(tokens) == 3:  # get_statuses page
            return [_status(sid="1")]
        if len(tokens) == 4:  # get_status
            return _status(sid="1")
        return {}  # check probe

    cfg = {"mastodon_token": "secret"}
    with patch.object(m, "_get_json", side_effect=fake_get_json):
        ch.lookup_account("@kate@mstdn.social", config=cfg)
        ch.get_statuses("@kate@mstdn.social", limit=1, config=cfg)
        ch.get_status("https://mstdn.social/@kate/1", config=cfg)
        ch.check(config=cfg)

    assert tokens == ["", "", "", "", ""]


# --- get_statuses ---

def test_get_statuses_maps_fields_and_marks_reposts():
    ch = MastodonChannel()
    pages = [
        _account(),
        [
            _status(sid="1", content="first"),
            _status(
                sid="2",
                acct="alice",
                content="boosted",
                reblog=_status(sid="9", acct="alice", content="original"),
                url="https://mstdn.social/@kate/2",
            ),
        ],
    ]
    with patch.object(m, "_get_json", side_effect=pages):
        statuses = ch.get_statuses("@kate@mstdn.social", config={})

    assert statuses[0]["kind"] == "post"
    assert statuses[0]["content"] == "first"
    assert statuses[0]["date"] == "2026-01-02"
    assert statuses[0]["author"] == "kate@mstdn.social"
    assert statuses[1]["kind"] == "repost"
    assert statuses[1]["author"] == "alice@mstdn.social"
    assert statuses[1]["content"] == "original"


def test_get_statuses_paginates_with_max_id_and_respects_limit():
    ch = MastodonChannel()
    page1 = [_status(sid=str(i)) for i in range(40)]
    page2 = [_status(sid=str(40 + i)) for i in range(5)]
    captured = []

    def fake_get_json(url, token=""):
        captured.append(url)
        if len(captured) == 1:
            return _account()
        return page1 if len(captured) == 2 else page2

    with patch.object(m, "_get_json", side_effect=fake_get_json), patch.object(
        m, "_PAGE_SLEEP", 0
    ):
        statuses = ch.get_statuses("@kate@mstdn.social", limit=45, config={})

    assert len(statuses) == 45
    lookup, first, second = (urlsplit(u) for u in captured)
    assert lookup.path == "/api/v1/accounts/lookup"
    assert parse_qs(first.query)["limit"] == ["40"]
    assert "max_id" not in parse_qs(first.query)
    assert parse_qs(second.query)["limit"] == ["5"]
    assert parse_qs(second.query)["max_id"] == ["39"]  # last id of page 1
    for part in (first, second):
        assert part.path == "/api/v1/accounts/7/statuses"
        assert parse_qs(part.query)["exclude_replies"] == ["true"]


def test_get_statuses_can_include_replies():
    ch = MastodonChannel()
    captured = []

    def fake_get_json(url, token=""):
        captured.append(url)
        return _account() if len(captured) == 1 else []

    with patch.object(m, "_get_json", side_effect=fake_get_json):
        ch.get_statuses("@kate@mstdn.social", exclude_replies=False, config={})

    query = parse_qs(urlsplit(captured[1]).query)
    assert "exclude_replies" not in query


def test_get_statuses_stops_at_empty_batch():
    ch = MastodonChannel()
    with patch.object(m, "_get_json", side_effect=[_account(), []]):
        statuses = ch.get_statuses("@kate@mstdn.social", config={})
    assert statuses == []


# --- get_status ---

def test_get_status_fetches_single_status_by_url():
    ch = MastodonChannel()
    captured = {}

    def fake_get_json(url, token=""):
        captured["url"] = url
        return _status(sid="123")

    with patch.object(m, "_get_json", side_effect=fake_get_json):
        status = ch.get_status("https://mstdn.social/@kate/123", config={})

    parts = urlsplit(captured["url"])
    assert parts.hostname == "mstdn.social"
    assert parts.path == "/api/v1/statuses/123"
    assert status["id"] == "123"
    assert status["kind"] == "post"
    assert status["content"] == "hello"


def test_get_status_remote_display_url_queries_url_host():
    ch = MastodonChannel()
    captured = {}

    def fake_get_json(url, token=""):
        captured["url"] = url
        return _status(sid="55")

    # "/@user@remote/<id>" is a display form: the numeric id is local to the
    # URL HOST, so the host is queried — never re-resolved to the remote.
    with patch.object(m, "_get_json", side_effect=fake_get_json):
        ch.get_status("https://mastodon.social/@bob@hci-social.org/55", config={})

    parts = urlsplit(captured["url"])
    assert parts.hostname == "mastodon.social"
    assert parts.path == "/api/v1/statuses/55"


def test_get_status_rejects_profile_url():
    ch = MastodonChannel()
    with pytest.raises(ValueError, match="status URL"):
        ch.get_status("https://mstdn.social/@kate", config={})


# --- search: federated search needs a token, degrades to exact-handle lookup ---

def test_search_with_token_uses_federated_account_search():
    ch = MastodonChannel()
    captured = {}

    def fake_get_json(url, token=""):
        captured["url"] = url
        captured["token"] = token
        return {"accounts": [_account()]}

    with patch.object(m, "_get_json", side_effect=fake_get_json):
        results = ch.search(
            "kate starbird", instance="mstdn.social", limit=5, config={"mastodon_token": "tok"}
        )

    parts = urlsplit(captured["url"])
    assert parts.hostname == "mstdn.social"
    assert parts.path == "/api/v2/search"
    query = parse_qs(parts.query)
    assert query["q"] == ["kate starbird"]
    assert query["type"] == ["accounts"]
    assert query["limit"] == ["5"]
    assert captured["token"] == "tok"
    assert results[0]["handle"] == "kate@mstdn.social"


def test_search_without_token_degrades_to_exact_handle_lookup():
    ch = MastodonChannel()
    captured = []

    def fake_get_json(url, token=""):
        captured.append(url)
        return _account()

    with patch.object(m, "_get_json", side_effect=fake_get_json):
        results = ch.search("@kate@mstdn.social", config={})

    assert len(results) == 1
    assert results[0]["handle"] == "kate@mstdn.social"
    parts = urlsplit(captured[0])
    assert parts.hostname == "mstdn.social"
    assert parts.path == "/api/v1/accounts/lookup"


def test_search_without_token_fuzzy_query_returns_error_offline():
    ch = MastodonChannel()
    with patch.object(m, "_get_json", side_effect=AssertionError("must not hit network")):
        results = ch.search("kate starbird", config={})
    assert len(results) == 1
    assert "error" in results[0]
    assert "MASTODON_TOKEN" in results[0]["error"]
    assert '@user@mastodon.social' in results[0]["error"]  # exact-handle hint


def test_search_empty_query_returns_error_offline():
    ch = MastodonChannel()
    with patch.object(m, "_get_json", side_effect=AssertionError("must not hit network")):
        results = ch.search("  ", config={})
    assert "error" in results[0]


# --- read(): URL routing ---

def test_read_profile_url_returns_account_and_recent_statuses():
    ch = MastodonChannel()
    # read() looks up the account, and get_statuses() re-resolves it before paging
    with patch.object(m, "_get_json", side_effect=[_account(), _account(), [_status(sid="1")]]):
        result = ch.read("https://mstdn.social/@kate/", config={})

    assert result["account"]["handle"] == "kate@mstdn.social"
    assert len(result["recent_statuses"]) == 1


def test_read_status_url_returns_single_status():
    ch = MastodonChannel()
    with patch.object(m, "_get_json", side_effect=[_status(sid="42")]) as fake:
        result = ch.read("https://mstdn.social/@kate/42", config={})
    assert result["id"] == "42"
    assert fake.call_count == 1  # no account lookup needed


def test_read_rejects_non_mastodon_url():
    ch = MastodonChannel()
    with pytest.raises(ValueError, match="Mastodon URL"):
        ch.read("https://example.com/foo", config={})


# --- strip_html ---

def test_strip_html_converts_blocks_and_decodes_entities():
    # "<p>" contributes a newline on both open and close tags (same as the
    # original script), so adjacent paragraphs are separated by a blank line.
    assert m.strip_html("<p>a</p><p>b</p>") == "a\n\nb"
    assert m.strip_html("a &amp; b &lt;c&gt;") == "a & b <c>"
    assert m.strip_html("<p>x</p><script>evil()</script><style>s</style>") == "x"


# --- token resolution ---

def test_mastodon_token_prefers_config_over_env():
    with patch.dict(os.environ, {"MASTODON_TOKEN": "env-tok"}):
        # explicit dict config wins (and stays hermetic — dicts don't read env)
        assert m._mastodon_token({"mastodon_token": "cfg-tok"}) == "cfg-tok"
        # no explicit config -> real Config falls back to the env var
        assert m._mastodon_token(None) == "env-tok"


def test_mastodon_token_missing_returns_empty():
    env = {k: v for k, v in os.environ.items() if k != "MASTODON_TOKEN"}
    with patch.dict(os.environ, env, clear=True):
        assert m._mastodon_token({}) == ""

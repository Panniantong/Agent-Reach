# -*- coding: utf-8 -*-
"""Unified entry: backend fallback, error selection, JSON contract, routing, parsers."""

import json
import time
import urllib.error

import pytest

from agent_reach.channels.base import Action, Channel, Param
from agent_reach.channels.github import _parse_target
from agent_reach.channels.v2ex import _parse_topic_id
from agent_reach.channels.web import _parse_exa_text
from agent_reach.channels.youtube import vtt_to_text
from agent_reach.runtime import cli as unified
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import ReachError, classify

ENVELOPE_KEYS = {"schema_version", "ok", "channel", "action", "backend", "items", "meta", "error"}


class FakeChannel(Channel):
    name = "fake"
    description = "fake"
    level = "default"
    actions = (
        Action(
            "search",
            "search",
            (Param("query", "q"), Param("limit", "n", required=False, type=int, default=3)),
            (("first", "_first"), ("second", "_second")),
            live_test={"query": "x"},
        ),
        Action("read", "read", (Param("target", "t"),), (("first", "_first_read"),)),
    )

    def __init__(self, first=None, second=None):
        self.first = first or (lambda **kw: [{"title": "first"}])
        self.second = second or (lambda **kw: [{"title": "second"}])
        self.calls = []

    def can_handle(self, url):
        return "fake.test" in url

    def _first(self, **kw):
        self.calls.append(("first", kw))
        return self.first(**kw)

    def _second(self, **kw):
        self.calls.append(("second", kw))
        return self.second(**kw)

    def _first_read(self, **kw):
        return [{"title": kw["target"]}]


def _raise(code):
    def fn(**kw):
        raise ReachError(code, code.lower())
    return fn


# ── dispatcher ──


def test_falls_back_to_next_backend_on_retryable_error():
    ch = FakeChannel(first=_raise("TIMEOUT"))
    out = run_action(ch, "search", {"query": "q"})
    assert out["ok"] is True
    assert out["backend"] == "second"
    assert [a["result"] for a in out["meta"]["attempts"]] == ["TIMEOUT", "ok"]


def test_not_found_stops_without_trying_other_backends():
    ch = FakeChannel(first=_raise("NOT_FOUND"))
    out = run_action(ch, "search", {"query": "q"})
    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_FOUND"
    assert [name for name, _ in ch.calls] == ["first"]


def test_real_failure_is_reported_over_not_installed():
    ch = FakeChannel(first=_raise("NEED_SETUP"), second=_raise("UPSTREAM_BROKEN"))
    out = run_action(ch, "search", {"query": "q"})
    assert out["error"]["code"] == "UPSTREAM_BROKEN"


def test_all_backends_missing_reports_need_setup():
    ch = FakeChannel(first=_raise("NEED_SETUP"), second=_raise("NEED_SETUP"))
    assert run_action(ch, "search", {"query": "q"})["error"]["code"] == "NEED_SETUP"


def test_params_are_validated_and_defaulted_before_any_backend_runs():
    ch = FakeChannel()
    assert run_action(ch, "search", {})["error"]["code"] == "BAD_INPUT"
    assert run_action(ch, "search", {"query": "q", "limit": "many"})["error"]["code"] == "BAD_INPUT"
    assert ch.calls == []
    run_action(ch, "search", {"query": "q"})
    assert ch.calls[0][1]["limit"] == 3


def test_unknown_action_lists_valid_actions():
    out = run_action(FakeChannel(), "nope", {})
    assert out["error"]["code"] == "BAD_INPUT"
    assert "search" in out["error"]["message"] and "read" in out["error"]["message"]


def test_hung_backend_is_abandoned_at_the_deadline():
    ch = FakeChannel(first=lambda **kw: time.sleep(5) or [], second=lambda **kw: [{"title": "x"}])
    started = time.monotonic()
    out = run_action(ch, "search", {"query": "q"}, timeout=0.3)
    assert time.monotonic() - started < 3
    assert out["ok"] is False
    assert out["error"]["code"] == "TIMEOUT"


def test_unexpected_exception_becomes_upstream_broken():
    ch = FakeChannel(first=lambda **kw: 1 / 0, second=_raise("NEED_SETUP"))
    out = run_action(ch, "search", {"query": "q"})
    assert out["error"]["code"] == "UPSTREAM_BROKEN"
    assert "ZeroDivisionError" in out["error"]["message"]


@pytest.mark.parametrize(
    "exc, code",
    [
        (urllib.error.HTTPError("u", 404, "nf", {}, None), "NOT_FOUND"),
        (urllib.error.HTTPError("u", 429, "rl", {}, None), "RATE_LIMITED"),
        (urllib.error.HTTPError("u", 500, "x", {}, None), "UPSTREAM_BROKEN"),
        (urllib.error.URLError(TimeoutError()), "TIMEOUT"),
        (FileNotFoundError("gh"), "NEED_SETUP"),
    ],
)
def test_classify_maps_upstream_failures(exc, code):
    assert classify(exc).code == code


def test_error_messages_do_not_leak_url_credentials():
    err = classify(RuntimeError("failed https://user:secret@example.com/x?token=abc123"))
    assert "secret" not in err.message and "abc123" not in err.message


# ── CLI contract ──


@pytest.fixture
def fake_cli(monkeypatch):
    ch = FakeChannel()
    monkeypatch.setattr(unified, "get_all_channels", lambda: [ch])
    return ch


def _run(capsys, argv):
    code = unified.main(argv)
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1, "unified commands print exactly one JSON line"
    return code, json.loads(lines[0])


def test_action_prints_one_envelope_and_exits_zero(capsys, fake_cli):
    code, out = _run(capsys, ["fake", "search", "two", "words", "--limit", "2"])
    assert code == 0
    assert set(out) == ENVELOPE_KEYS
    assert out["schema_version"] == 1
    assert fake_cli.calls[0][1]["query"] == "two words"
    assert fake_cli.calls[0][1]["limit"] == 2


def test_failures_still_print_an_envelope_and_exit_one(capsys, fake_cli):
    code, out = _run(capsys, ["fake", "search"])
    assert code == 1
    assert set(out) == ENVELOPE_KEYS
    assert out["error"]["code"] == "BAD_INPUT"
    assert "usage: agent-reach fake search <query>" in out["error"]["message"]


def test_read_routes_by_url(capsys, fake_cli):
    code, out = _run(capsys, ["read", "https://fake.test/a"])
    assert code == 0
    assert out["channel"] == "fake"
    assert out["items"][0]["title"] == "https://fake.test/a"


def test_handles_only_claims_unified_commands(fake_cli):
    assert unified.handles(["fake", "search"])
    assert unified.handles(["channels"])
    assert not unified.handles(["doctor"])
    assert not unified.handles(["check-update"])
    assert not unified.handles([])


def test_channels_lists_usage_for_agents(capsys, fake_cli):
    code, out = _run(capsys, ["channels"])
    assert code == 0
    action = out["channels"][0]["actions"][0]
    assert action["usage"] == "agent-reach fake search <query> [--limit LIMIT]"
    assert action["backends"] == ["first", "second"]


def test_check_passes_when_any_backend_works(capsys, fake_cli):
    fake_cli.first = _raise("TIMEOUT")
    code, out = _run(capsys, ["check"])
    assert code == 0
    assert [(r["backend"], r["passed"]) for r in out["results"]] == [("first", False), ("second", True)]


def test_check_fails_when_backend_returns_nothing(capsys, fake_cli):
    fake_cli.first = lambda **kw: []
    fake_cli.second = lambda **kw: []
    code, out = _run(capsys, ["check"])
    assert code == 1
    assert out["results"][0]["error"]["code"] == "EMPTY"


# ── parsers ──


def test_parse_exa_text_splits_results():
    text = (
        "Title: A\nURL: https://a.test\nPublished: N/A\nAuthor: Ann\nHighlights:\nbody a\n\n"
        "Title: B\nURL: https://b.test\nPublished: 2026-01-02\nAuthor: N/A\nbody b"
    )
    items = _parse_exa_text(text)
    assert [(i["title"], i["url"], i["author"], i["published_at"]) for i in items] == [
        ("A", "https://a.test", "Ann", None),
        ("B", "https://b.test", None, "2026-01-02"),
    ]
    assert items[0]["text"] == "body a"


def test_vtt_to_text_drops_timings_tags_and_rolling_repeats():
    vtt = (
        "WEBVTT\nKind: captions\nLanguage: en\n\n"
        "00:00:01.000 --> 00:00:02.000\n<c>hello</c> world\n\n"
        "00:00:02.000 --> 00:00:03.000\nhello world\n\n"
        "2\n00:00:03.000 --> 00:00:04.000\nnext &amp; last\n"
    )
    assert vtt_to_text(vtt) == "hello world\nnext & last"


@pytest.mark.parametrize(
    "target, expected",
    [
        ("yt-dlp/yt-dlp", ("yt-dlp", "yt-dlp", None)),
        ("https://github.com/cli/cli.git", ("cli", "cli", None)),
        ("https://github.com/cli/cli/issues/42", ("cli", "cli", 42)),
        ("https://github.com/cli/cli/pull/7?x=1", ("cli", "cli", 7)),
    ],
)
def test_github_target_forms(target, expected):
    assert _parse_target(target) == expected


@pytest.mark.parametrize("bad", ["not a target", "https://gitlab.com/a/b/c/d", "a/b/c"])
def test_github_rejects_other_targets(bad):
    with pytest.raises(ReachError) as info:
        _parse_target(bad)
    assert info.value.code == "BAD_INPUT"


def test_v2ex_topic_id_forms():
    assert _parse_topic_id("1000") == 1000
    assert _parse_topic_id("https://www.v2ex.com/t/1000#reply3") == 1000
    with pytest.raises(ReachError):
        _parse_topic_id("https://example.com/t/1000")

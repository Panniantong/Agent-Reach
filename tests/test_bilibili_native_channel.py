# -*- coding: utf-8 -*-
"""Bilibili channel wiring: native chains, fallback, subtitle params, setup problems."""

import inspect

import pytest

from agent_reach.channels import bilibili
from agent_reach.native import bilibili as native
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import ReachError

BV = "BV1GJ411x7h7"


def _channel():
    return bilibili.BilibiliChannel()


def _action(name):
    return next(action for action in bilibili.BilibiliChannel.actions if action.name == name)


def test_backend_chains_match_the_plan():
    assert _action("search").backends == (
        ("native", "_native_search"),
        ("bili-cli", "_cli_search"),
    )
    assert _action("read").backends == (
        ("bilibili-api", "_api_read"),
        ("native", "_native_read"),
        ("bili-cli", "_cli_read"),
    )
    assert _action("subtitle").backends == (
        ("native", "_native_subtitle"),
        ("bili-cli", "_cli_subtitle"),
    )
    assert _action("summary").backends == (("native", "_native_summary"),)
    assert _action("hot").backends == (
        ("bili-cli", "_cli_hot"),
        ("bilibili-api", "_api_hot"),
    )


def test_subtitle_declares_part_language_and_timestamps():
    params = {p.name: p for p in _action("subtitle").params}
    assert list(params) == ["target", "part", "language", "timestamps"]
    assert params["part"].type is int and params["part"].default == 1
    assert params["language"].default == "ai-zh"
    assert params["timestamps"].type is str and params["timestamps"].default == "true"


def test_summary_has_no_live_test():
    assert _action("summary").live_test is None


def test_cli_subtitle_signature_accepts_new_params():
    signature = inspect.signature(bilibili.BilibiliChannel._cli_subtitle)
    for name in ("target", "part", "language", "timestamps", "timeout"):
        assert name in signature.parameters


def test_search_native_only(monkeypatch):
    monkeypatch.setattr(native, "search", lambda query, limit, timeout: [{"title": query}])
    out = run_action(_channel(), "search", {"query": "Python", "limit": 2}, only_backend="native")
    assert out["ok"] is True
    assert out["backend"] == "native"
    assert out["items"] == [{"title": "Python"}]


def test_search_falls_back_to_bili_cli(monkeypatch):
    def broken(**kwargs):
        raise ReachError("UPSTREAM_BROKEN", "wbi failed")

    monkeypatch.setattr(native, "search", broken)
    monkeypatch.setattr(
        bilibili,
        "_bili_json",
        lambda args, timeout: [{"bvid": BV, "title": "来自 bili-cli", "owner": {"name": "UP"}}],
    )
    out = run_action(_channel(), "search", {"query": "Python", "limit": 3})
    assert out["ok"] is True
    assert out["backend"] == "bili-cli"
    assert [a["backend"] for a in out["meta"]["attempts"]] == ["native", "bili-cli"]


def test_read_404_stops_before_bili_cli(monkeypatch):
    bili_calls = []

    def api_broken(path, timeout):
        raise ReachError("UPSTREAM_BROKEN", "api unavailable")

    monkeypatch.setattr(bilibili, "_bili_api", api_broken)
    monkeypatch.setattr(native, "read", lambda target, timeout: _raise("NOT_FOUND"))
    monkeypatch.setattr(bilibili, "_bili_json", lambda args, timeout: bili_calls.append(args))

    out = run_action(_channel(), "read", {"target": BV})
    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_FOUND"
    assert bili_calls == []


def _raise(code):
    raise ReachError(code, code.lower())


def test_read_falls_back_native_then_bili_cli(monkeypatch):
    def api_broken(path, timeout):
        raise ReachError("UPSTREAM_BROKEN", "api unavailable")

    monkeypatch.setattr(bilibili, "_bili_api", api_broken)
    monkeypatch.setattr(native, "read", lambda target, timeout: _raise("TIMEOUT"))
    monkeypatch.setattr(
        bilibili,
        "_bili_json",
        lambda args, timeout: {"video": {"bvid": BV, "title": "cli", "owner": {"name": "UP"}}},
    )
    out = run_action(_channel(), "read", {"target": BV})
    assert out["ok"] is True
    assert out["backend"] == "bili-cli"
    assert [a["backend"] for a in out["meta"]["attempts"]] == [
        "bilibili-api",
        "native",
        "bili-cli",
    ]


def test_native_subtitle_receives_part_language_and_timestamps(monkeypatch):
    seen = {}

    def fake_subtitle(*, target, part, language, timestamps, timeout):
        seen.update(target=target, part=part, language=language, timestamps=timestamps)
        return [{"title": "字幕"}]

    monkeypatch.setattr(native, "subtitle", fake_subtitle)
    out = run_action(
        _channel(),
        "subtitle",
        {"target": BV, "part": 2, "language": "ai-en", "timestamps": "false"},
        only_backend="native",
    )
    assert out["ok"] is True and out["backend"] == "native"
    assert seen == {"target": BV, "part": 2, "language": "ai-en", "timestamps": "false"}


def test_subtitle_falls_back_to_bili_cli_for_default_params(monkeypatch):
    monkeypatch.setattr(native, "subtitle", lambda **kwargs: _raise("NEED_SETUP"))
    monkeypatch.setattr(bilibili, "_reuse_subtitle_login", lambda timeout: None)
    monkeypatch.setattr(
        bilibili,
        "_bili_json",
        lambda args, timeout: {
            "subtitle": {"available": True, "text": "bili-cli 字幕"},
            "video": {"bvid": BV, "title": "T", "owner": {"name": "UP"}},
        },
    )
    out = run_action(
        _channel(), "subtitle", {"target": BV, "part": 1, "language": "ai-zh", "timestamps": "true"}
    )
    assert out["ok"] is True
    assert out["backend"] == "bili-cli"
    assert [a["backend"] for a in out["meta"]["attempts"]] == ["native", "bili-cli"]


def test_cli_subtitle_refuses_params_it_cannot_honour(monkeypatch):
    monkeypatch.setattr(bilibili, "_reuse_subtitle_login", lambda timeout: None)
    monkeypatch.setattr(
        bilibili,
        "_bili_json",
        lambda args, timeout: pytest.fail("bili-cli must not run for unsupported params"),
    )
    for kwargs, fragment in (
        ({"part": 2}, "part 2"),
        ({"language": "ai-en"}, "ai-en"),
        ({"timestamps": "false"}, "omit timestamps"),
    ):
        with pytest.raises(ReachError) as exc:
            _channel()._cli_subtitle(target=BV, timeout=5, **kwargs)
        assert exc.value.code == "UPSTREAM_BROKEN"
        assert fragment in exc.value.message


def test_cli_subtitle_runs_with_default_params(monkeypatch):
    monkeypatch.setattr(bilibili, "_reuse_subtitle_login", lambda timeout: None)
    monkeypatch.setattr(
        bilibili,
        "_bili_json",
        lambda args, timeout: {
            "subtitle": {"available": True, "text": "public subtitle"},
            "video": {"bvid": BV, "title": "T", "owner": {"name": "UP"}},
        },
    )
    items = _channel()._cli_subtitle(
        target=BV, part=1, language="ai-zh", timestamps="true", timeout=5
    )
    assert items[0]["text"] == "public subtitle"


def test_summary_runs_native_only(monkeypatch):
    monkeypatch.setattr(native, "summary", lambda **kwargs: [{"title": "总结"}])
    out = run_action(_channel(), "summary", {"target": BV})
    assert out["ok"] is True
    assert out["backend"] == "native"
    assert [a["backend"] for a in out["meta"]["attempts"]] == ["native"]


def test_summary_forwards_part_language_and_model(monkeypatch):
    seen = {}

    def fake_summary(*, target, part, language, model, timeout):
        seen.update(target=target, part=part, language=language, model=model)
        return [{"title": "总结"}]

    monkeypatch.setattr(native, "summary", fake_summary)
    out = run_action(
        _channel(),
        "summary",
        {"target": BV, "part": 3, "language": "zh-Hans", "model": "custom/model"},
        only_backend="native",
    )
    assert out["ok"] is True
    assert seen == {
        "target": BV,
        "part": 3,
        "language": "zh-Hans",
        "model": "custom/model",
    }


def test_setup_problems_does_not_block_on_optional_summary_key(monkeypatch):
    monkeypatch.delenv("SUMMARY_API_KEY", raising=False)
    assert _channel().setup_problems() == []

import json
from unittest.mock import Mock

import pytest

from agent_reach.backends.opencli import _opencli_error, opencli_call
from agent_reach.channels.base import Action, Channel, Param
from agent_reach.channels.boss import BossChannel
from agent_reach.runtime import manage, state
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import ReachError
from agent_reach.runtime.run import CommandFailed


@pytest.mark.parametrize(
    "message,code",
    [
        ("您的环境存在异常，请重新登录", "PLATFORM_BLOCKED"),
        ("Boss rejected the current browser environment", "PLATFORM_BLOCKED"),
        ("HTTP 429", "RATE_LIMITED"),
        ("please login", "NEED_LOGIN"),
    ],
)
def test_error_classification_precedence(message, code):
    assert _opencli_error(json.dumps({"error": {"message": message}}), "").code == code


def test_opencli_never_retries_navigation(monkeypatch):
    monkeypatch.setattr("agent_reach.runtime.browser_binding.environment", lambda _: {"OPENCLI_PROFILE": "owned"})
    run = Mock(side_effect=CommandFailed("UPSTREAM_BROKEN", "failed", stderr="Navigation rejected"))
    monkeypatch.setattr("agent_reach.runtime.run.run_cmd", run)
    with pytest.raises(ReachError):
        opencli_call("boss", ["search", "Python"], timeout=1)
    assert run.call_count == 1


class SearchChannel(Channel):
    name = "fixture"
    level = "default"
    actions = (
        Action(
            "search",
            "search",
            (Param("query", "query"),),
            (("first", "first"), ("second", "second")),
            live_test={"query": "q"},
        ),
    )

    def can_handle(self, url):
        return False

    def first(self, **kw):
        return [{"title": "result"}]

    def second(self, **kw):
        raise AssertionError("unexpected fallback")


def test_search_acceptance_uses_normal_route_once(monkeypatch):
    ch = SearchChannel()
    monkeypatch.setattr(manage, "_channels", lambda: [ch])
    result = manage.run_checks(search_only=True)
    assert result["ok"] and len(result["results"]) == 1
    assert result["results"][0]["backend"] == "first"
    assert state.load()["checks"]["fixture"]["scope"] == "search"
    assert manage.channel_status(ch, state.load())["status"] == "search_ready"


@pytest.mark.parametrize("code", ["PLATFORM_BLOCKED", "RATE_LIMITED", "NEED_LOGIN"])
def test_blocking_errors_never_switch_backend(code):
    ch = SearchChannel()

    def fail(**kw):
        raise ReachError(code, "blocked")

    ch.first = fail
    result = run_action(ch, "search", {"query": "x"})
    assert result["error"]["code"] == code
    assert len(result["meta"]["attempts"]) == 1


def test_boss_native_cdp_maps_results(monkeypatch):
    import json
    ch = BossChannel()
    assert ("boss-agent-cli", "_cli_search") in ch.actions[0].backends
    monkeypatch.setattr("agent_reach.runtime.onboarding.require_boss_cdp", lambda: "http://127.0.0.1:9222")
    monkeypatch.setattr("agent_reach.channels.boss.resolve", lambda _: "/test/bin/boss")
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        return json.dumps({"ok": True, "data": [{"title": "Engineer", "company": "Company", "job_id": "test"}]})
    monkeypatch.setattr("agent_reach.channels.boss.run_cmd", run)
    out = run_action(ch, "search", {"query": "Python", "limit": 1}, only_backend="boss-agent-cli")
    assert out["ok"] and out["items"][0]["author"] == "Company"
    payload = json.loads(calls[0][-1])
    assert payload["cdp_url"] == "http://127.0.0.1:9222"
    assert calls[0][1].endswith("boss_native.py")


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_budget_cannot_start_work(timeout):
    assert (
        run_action(SearchChannel(), "search", {"query": "x"}, timeout=timeout)["error"]["code"]
        == "BAD_INPUT"
    )


def test_profile_lock_is_released_and_other_profiles_independent():
    from agent_reach.runtime.browser_binding import execution_lock

    with execution_lock("one"):
        with pytest.raises(ReachError) as exc:
            with execution_lock("one"):
                pass
        assert exc.value.code == "BUSY"
        with execution_lock("two"):
            pass
    with execution_lock("one"):
        pass








def test_search_checks_stop_after_platform_block(monkeypatch):
    ch = SearchChannel()

    def fail(**kw):
        raise ReachError("PLATFORM_BLOCKED", "blocked")

    ch.first = fail
    monkeypatch.setattr(manage, "_channels", lambda: [ch])
    result = manage.run_checks()
    assert not result["ok"]
    assert len(result["results"]) == 1




def test_boss_native_risk_stops_without_retry(monkeypatch):
    monkeypatch.setattr("agent_reach.runtime.onboarding.require_boss_cdp", lambda: "http://127.0.0.1:9222")
    monkeypatch.setattr("agent_reach.channels.boss.resolve", lambda _: "/test/bin/boss")
    run = Mock(return_value=json.dumps({"ok": False, "error": {"code": "ACCOUNT_RISK", "message": "environment risk code 37"}}))
    monkeypatch.setattr("agent_reach.channels.boss.run_cmd", run)
    out = run_action(BossChannel(), "search", {"query": "Python"})
    assert out["error"]["code"] == "PLATFORM_BLOCKED"
    assert run.call_count == 1


def test_failed_backend_is_remembered_and_explicit_diagnostic_recovers():
    ch = SearchChannel()
    calls = []

    def fail(**kwargs):
        calls.append("first")
        raise ReachError("TIMEOUT", "page did not appear")

    ch.first = fail
    ch.second = lambda **kwargs: [{"title": "fallback"}]
    assert run_action(ch, "search", {"query": "one"})["backend"] == "second"
    again = run_action(ch, "search", {"query": "two"})
    assert again["backend"] == "second" and calls == ["first"]
    assert again["meta"]["attempts"][0]["skipped"] is True
    saved = state.load()["backend_health"]["fixture"]["search"]["first"]
    assert set(saved) == {"code", "at", "fingerprint"}
    assert saved["code"] == "TIMEOUT"
    ch.first = lambda **kwargs: [{"title": "recovered"}]
    assert run_action(ch, "search", {"query": "three"}, only_backend="first")["ok"]
    assert "first" not in state.load()["backend_health"]["fixture"]["search"]
    assert run_action(ch, "search", {"query": "four"})["backend"] == "first"


def test_technical_pause_expires_when_configuration_changes(monkeypatch):
    signature = ["old"]
    monkeypatch.setattr(manage, "fingerprint", lambda channel: signature[0])
    ch = SearchChannel()
    ch.first = lambda **kwargs: (_ for _ in ()).throw(ReachError("UPSTREAM_BROKEN", "failed"))
    ch.second = lambda **kwargs: [{"title": "fallback"}]
    run_action(ch, "search", {"query": "one"})
    signature[0] = "new"
    ch.first = lambda **kwargs: [{"title": "repaired"}]
    assert run_action(ch, "search", {"query": "two"})["backend"] == "first"


def test_cached_failure_does_not_hide_a_new_fallback_error():
    ch = SearchChannel()
    ch.first = lambda **kwargs: (_ for _ in ()).throw(ReachError("TIMEOUT", "old failure"))
    ch.second = lambda **kwargs: [{"title": "fallback"}]
    run_action(ch, "search", {"query": "one"})
    ch.second = lambda **kwargs: (_ for _ in ()).throw(ReachError("UPSTREAM_BROKEN", "current failure"))
    out = run_action(ch, "search", {"query": "two"})
    assert out["meta"]["attempts"][0]["skipped"]
    assert out["error"]["message"] == "current failure"


def test_technical_pause_expires_without_affecting_other_actions():
    ch = SearchChannel()
    ch.actions += (Action("read", "read", (Param("target", "target"),), (("first", "first"),)),)
    ch.first = lambda **kwargs: (_ for _ in ()).throw(ReachError("TIMEOUT", "failed"))
    ch.second = lambda **kwargs: [{"title": "fallback"}]
    run_action(ch, "search", {"query": "one"})
    ch.first = lambda **kwargs: [{"title": "now working"}]
    assert run_action(ch, "read", {"target": "https://example.test"})["backend"] == "first"
    state.mutate(lambda data: data["backend_health"]["fixture"]["search"]["first"].__setitem__(
        "at", "2020-01-01T00:00:00Z"))
    assert run_action(ch, "search", {"query": "two"})["backend"] == "first"


def test_direct_dispatch_cannot_bypass_confirmed_platform_cooldown():
    ch = SearchChannel()
    ch.first = lambda **kwargs: (_ for _ in ()).throw(ReachError("RATE_LIMITED", "HTTP 429"))
    assert run_action(ch, "search", {"query": "one"})["error"]["code"] == "RATE_LIMITED"
    ch.first = Mock(side_effect=AssertionError("must remain paused"))
    forced = run_action(ch, "search", {"query": "two"}, only_backend="first")
    assert forced["error"]["code"] == "RATE_LIMITED"
    assert forced["meta"]["attempts"] == []
    ch.first.assert_not_called()


def test_browser_pacing_respects_budget_without_claiming_platform_rate_limit(monkeypatch):
    from agent_reach.runtime import dispatch

    ch = SearchChannel()
    ch.actions = (Action("search", "search", (Param("query", "query"),),
                         (("opencli", "first"), ("second", "second"))),)
    state.mutate(lambda data: data.setdefault("request_starts", {}).__setitem__(ch.name, state.now()))
    monkeypatch.setattr(dispatch.state, "age_seconds", lambda stamp: 0 if stamp else float("inf"))
    ch.first = Mock(side_effect=AssertionError("no budget for paced request"))
    out = run_action(ch, "search", {"query": "x"}, timeout=1)
    assert out["error"]["code"] == "TIMEOUT"
    assert not state.load().get("cooldowns")
    assert not state.load().get("backend_health")
    ch.first.assert_not_called()


def test_empty_search_succeeds_but_live_acceptance_remains_unverified(monkeypatch):
    ch = SearchChannel()
    ch.first = lambda **kwargs: []
    monkeypatch.setattr(manage, "_channels", lambda: [ch])
    assert run_action(ch, "search", {"query": "none"})["ok"] is True
    result = manage.run_checks(search_only=True)
    assert result["ok"] is False
    assert result["results"][0]["passed"] is False
    assert result["results"][0]["verified"] is False
    assert result["results"][0]["error"]["code"] == "EMPTY"
    assert manage.channel_status(ch, state.load())["status"] == "broken"

import json
from unittest.mock import Mock

import pytest

from agent_reach.backends.opencli import _opencli_error, opencli_call
from agent_reach.channels.base import Action, Channel, Param
from agent_reach.channels.boss import BossChannel
from agent_reach.runtime import manage, state
from agent_reach.runtime.browser_binding import (
    bind_profile,
    environment,
    profile_for,
    unbind_profile,
)
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import ReachError
from agent_reach.runtime.run import CommandFailed


def test_bindings_are_per_channel_and_unbind_preserves_browser(monkeypatch):
    launch = Mock(side_effect=AssertionError("must not launch"))
    monkeypatch.setattr("agent_reach.runtime.browser.ensure_running", launch)
    bind_profile("boss", "work")
    bind_profile("twitter", "personal")
    assert environment("boss")["OPENCLI_PROFILE"] == "work"
    assert environment("twitter")["OPENCLI_PROFILE"] == "personal"
    unbind_profile("boss")
    assert profile_for("boss") is None
    assert profile_for("twitter") == "personal"
    launch.assert_not_called()


def test_empty_override_does_not_fall_back(monkeypatch):
    bind_profile("boss", "work")
    monkeypatch.setenv("AGENT_REACH_OPENCLI_PROFILE", "")
    with pytest.raises(ReachError, match="non-empty"):
        environment("boss")


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
    bind_profile("boss", "work")
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


def test_rebinding_invalidates_previous_acceptance():
    data = state.load()
    data["checks"]["boss"] = {"actions": {"search": True}}
    state.save(data)
    bind_profile("boss", "new")
    assert "boss" not in state.load()["checks"]


def test_patch_rejects_unknown_version_without_writes(tmp_path):
    from agent_reach.runtime.opencli_compat import repair

    (tmp_path / "package.json").write_text('{"version":"unknown"}')
    before = set(tmp_path.iterdir())
    with pytest.raises(ReachError):
        repair(tmp_path)
    assert set(tmp_path.iterdir()) == before


def test_linkedin_passes_budget_to_mcporter(monkeypatch):
    from agent_reach.channels import linkedin

    monkeypatch.setattr(linkedin, "_own_servers", lambda: {"linkedin": {}})
    run = Mock(
        return_value='{"job_ids":["123"],"references":{"search_results":[{"url":"/jobs/view/123/","text":"Engineer"}]}}'
    )
    monkeypatch.setattr(linkedin, "run_cmd", run)
    rows = linkedin.LinkedInChannel()._mcp_jobs(query="Python", location=None, limit=1, timeout=120)
    assert run.call_args.kwargs["env"]["MCPORTER_CALL_TIMEOUT"] == "120000"
    assert rows[0]["title"] == "Engineer"


def test_search_checks_stop_after_platform_block(monkeypatch):
    ch = SearchChannel()

    def fail(**kw):
        raise ReachError("PLATFORM_BLOCKED", "blocked")

    ch.first = fail
    monkeypatch.setattr(manage, "_channels", lambda: [ch])
    result = manage.run_checks()
    assert not result["ok"]
    assert len(result["results"]) == 1


def test_login_and_logout_do_not_touch_daily_browser(monkeypatch, capsys):
    from agent_reach.runtime import cli

    bind_profile("twitter", "work")
    monkeypatch.setattr(
        "agent_reach.runtime.browser.start",
        Mock(side_effect=AssertionError("unexpected browser launch")),
    )
    assert cli.main(["login", "twitter"]) == 0
    login = json.loads(capsys.readouterr().out)
    assert login["result"]["logged_in"] is None
    assert cli.main(["logout", "twitter"]) == 0
    logout = json.loads(capsys.readouterr().out)
    assert logout["items"][0]["browser_cookies_changed"] is False
    assert profile_for("twitter") == "work"


def test_boss_native_risk_stops_without_retry(monkeypatch):
    monkeypatch.setattr("agent_reach.runtime.onboarding.require_boss_cdp", lambda: "http://127.0.0.1:9222")
    monkeypatch.setattr("agent_reach.channels.boss.resolve", lambda _: "/test/bin/boss")
    run = Mock(return_value=json.dumps({"ok": False, "error": {"code": "ACCOUNT_RISK", "message": "environment risk code 37"}}))
    monkeypatch.setattr("agent_reach.channels.boss.run_cmd", run)
    out = run_action(BossChannel(), "search", {"query": "Python"})
    assert out["error"]["code"] == "PLATFORM_BLOCKED"
    assert run.call_count == 1

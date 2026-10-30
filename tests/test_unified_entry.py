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


def test_unknown_command_is_bad_input(capsys, fake_cli):
    for argv in (["install"], ["check-update"], ["nosuchchannel", "search", "x"]):
        code, out = _run(capsys, argv)
        assert code == 1
        assert out["ok"] is False
        assert out["error"]["code"] == "BAD_INPUT"
        assert "agent-reach help" in out["error"]["message"]


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


def test_skill_command_links_a_skills_dir_and_reports_it(capsys, fake_cli):
    from agent_reach.utils.paths import home_dir

    target = home_dir() / "my-ai" / "skills"
    code, out = _run(capsys, ["skill", "link", str(target)])
    assert code == 0 and out["action"] == "skill link"
    assert out["result"]["links"] == [str(target / "agent-reach")]
    code, out = _run(capsys, ["skill"])
    assert code == 0 and out["result"]["installed"] is True
    code, out = _run(capsys, ["skill", "unlink"])
    assert code == 1 and out["error"]["code"] == "BAD_INPUT"


def test_doctor_reports_regressed_per_channel(capsys, fake_cli):
    code, out = _run(capsys, ["doctor"])
    assert code == 0
    assert out["result"]["channels"][0]["regressed"] is False


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


# ── login state under ~/.agent-reach/sessions ──


class SessionChannel(FakeChannel):
    name = "sess"
    session = "fake-tool"
    login_argv = ("fake-login",)
    legacy_state = (".fake-tool",)


@pytest.fixture
def session_cli(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    ch = SessionChannel()
    monkeypatch.setattr(unified, "get_all_channels", lambda: [ch, FakeChannel()])
    return tmp_path


def test_session_env_points_tool_home_into_agent_reach(session_cli):
    from agent_reach.runtime.sessions import session_env

    env = session_env("fake-tool")
    assert env["HOME"] == str(session_cli / ".agent-reach" / "sessions" / "fake-tool")


def test_import_existing_copies_old_login_only_on_request(capsys, session_cli):
    old = session_cli / ".fake-tool"
    old.mkdir()
    (old / "credential.json").write_text("{}")
    code, out = _run(capsys, ["login", "sess", "--import-existing"])
    assert code == 0
    assert (session_cli / ".agent-reach" / "sessions" / "fake-tool" / ".fake-tool" / "credential.json").exists()
    assert old.exists(), "the original login is left untouched"


def test_logout_removes_only_that_session(capsys, session_cli):
    from agent_reach.runtime.sessions import session_dir

    (session_dir("fake-tool") / "x").write_text("1")
    (session_dir("other") / "y").write_text("1")
    code, out = _run(capsys, ["logout", "sess"])
    assert code == 0 and out["items"] == [{"removed": True}]
    assert not (session_cli / ".agent-reach" / "sessions" / "fake-tool").exists()
    assert (session_cli / ".agent-reach" / "sessions" / "other" / "y").exists()


def test_login_rejects_channels_without_managed_login(capsys, session_cli):
    code, out = _run(capsys, ["login", "fake"])
    assert code == 1 and out["error"]["code"] == "BAD_INPUT"


def test_channels_reports_login_status(capsys, session_cli):
    from agent_reach.runtime.sessions import session_dir

    _, out = _run(capsys, ["channels"])
    sess = next(c for c in out["channels"] if c["name"] == "sess")
    assert sess["login"] == {"via": "session", "logged_in": False, "command": "agent-reach login sess"}
    assert next(c for c in out["channels"] if c["name"] == "fake")["login"] is None
    (session_dir("fake-tool") / "cookie").write_text("1")
    _, out = _run(capsys, ["channels"])
    assert next(c for c in out["channels"] if c["name"] == "sess")["login"]["logged_in"] is True


# ── Agent Reach dedicated browser ──


@pytest.fixture
def fake_browser(monkeypatch, tmp_path):
    from agent_reach.runtime import browser

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(browser, "can_load_extension", lambda: True)  # the macOS/Linux path; Windows has its own test
    state = {"contexts": ["daily"], "running": True, "opened": [], "launches": 0, "launch_delay": 0.0,
             "watched": False}

    def fake_launch(url, *, headless=True):
        browser.update_state(headless=headless)
        state["launches"] += 1
        time.sleep(state["launch_delay"])
        state["running"] = True
        state["watched"] = True  # a real launch starts the owning watcher
        state["contexts"].append("dedicated")

    def fake_stop(timeout=10.0):
        state["running"] = False
        state["watched"] = False
        if "dedicated" in state["contexts"]:
            state["contexts"].remove("dedicated")
        return True

    real_watcher_running = browser.watcher_running
    monkeypatch.setattr(browser, "connected_contexts", lambda: list(state["contexts"]))
    # The dedicated profile's own saved OpenCLI id, readable only while it runs.
    monkeypatch.setattr(browser, "dedicated_context", lambda: "dedicated" if state["running"] else None)
    monkeypatch.setattr(browser, "is_running", lambda: state["running"])
    monkeypatch.setattr(browser, "_profile_pids", lambda: [999] if state["running"] else [])
    monkeypatch.setattr(browser, "watcher_running", lambda: state["watched"] or real_watcher_running())
    monkeypatch.setattr(browser, "start", lambda url="about:blank": state["opened"].append(url))
    monkeypatch.setattr(browser, "_launch", fake_launch)
    monkeypatch.setattr(browser, "stop", fake_stop)
    monkeypatch.setattr(browser, "ensure_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(browser, "refresh_extension", lambda: {"version": "1.0.0", "updated": False})
    monkeypatch.setattr(browser, "_RUNNING_GRACE", 0.0)
    return state


def _bind_dedicated(fake_browser):
    from agent_reach.runtime import browser

    fake_browser["contexts"].append("dedicated")
    assert browser.bind()["status"] == "ready"


def test_browser_action_sets_up_unbound_browser_by_itself(fake_browser):
    from agent_reach.runtime import browser
    from agent_reach.runtime.browser_binding import environment

    fake_browser["running"] = False
    assert environment("reddit") ["OPENCLI_PROFILE"] == "dedicated"  # no NEED_SETUP, no user click
    assert browser.bound_context() == "dedicated"  # the user's own "daily" profile is never picked
    assert fake_browser["launches"] == 1

    assert environment("reddit") ["OPENCLI_PROFILE"] == "dedicated"
    assert fake_browser["launches"] == 1  # already open: no second browser

    browser.stop()
    assert environment("reddit") ["OPENCLI_PROFILE"] == "dedicated"
    assert fake_browser["launches"] == 2  # closed: reopened, not set up again
    assert browser.last_used() is not None


def test_browser_cold_start_does_not_count_against_timeout(fake_browser):
    from agent_reach.runtime import browser

    _bind_dedicated(fake_browser)
    fake_browser["running"] = False
    fake_browser["contexts"].remove("dedicated")
    fake_browser["launch_delay"] = 1.5
    seen = {}

    def opencli_backend(**kw):
        browser.ensure_running("dedicated")
        seen["timeout"] = kw["timeout"]
        time.sleep(0.5)
        return [{"title": "ok"}]

    ch = FakeChannel(first=opencli_backend, second=_raise("UPSTREAM_BROKEN"))
    out = run_action(ch, "search", {"query": "q"}, timeout=1.0)
    assert out["ok"] is True, out
    assert out["backend"] == "first"
    assert fake_browser["launches"] == 1


def test_concurrent_actions_start_one_browser(fake_browser):
    import threading

    from agent_reach.runtime import browser

    _bind_dedicated(fake_browser)
    fake_browser["running"] = False
    fake_browser["contexts"].remove("dedicated")
    fake_browser["launch_delay"] = 0.5
    errors = []

    def call():
        try:
            browser.ensure_running("dedicated")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=call) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert errors == []
    assert fake_browser["launches"] == 1


def test_only_one_idle_watcher_and_it_closes_idle_browser(fake_browser, monkeypatch):
    import threading

    from agent_reach.runtime import browser, browser_watcher

    stopped = []

    def fake_stop(timeout=10.0):
        stopped.append(time.time())
        fake_browser["running"] = False
        return True

    monkeypatch.setattr(browser, "stop", fake_stop)
    browser.touch()
    result = {}
    first = threading.Thread(target=lambda: result.setdefault("first", browser_watcher.watch(idle=3.0, poll=0.1)))
    first.start()
    assert browser.wait_for(browser.watcher_running, 2.0, interval=0.05)
    assert browser_watcher.watch(idle=3.0, poll=0.1) == "another watcher is running"
    first.join(8)
    assert result["first"] == "closed after idle"
    assert len(stopped) == 1
    assert not browser.watcher_running()


def test_idle_watcher_exits_when_browser_is_closed(fake_browser):
    from agent_reach.runtime import browser_watcher

    fake_browser["running"] = False
    assert browser_watcher.watch(idle=600, poll=0.1) == "browser closed"


def test_bind_waits_for_the_dedicated_browsers_own_profile(fake_browser):
    from agent_reach.runtime import browser

    fake_browser["contexts"].append("other")  # another Chrome with the extension connects first
    assert browser.bind()["status"] == "waiting_for_extension"
    assert browser.bound_context() is None
    fake_browser["contexts"].append("dedicated")
    assert browser.bind() == {"status": "ready", "context": "dedicated"}
    assert browser.bound_context() == "dedicated"


def test_setup_never_binds_the_users_chrome_reconnecting_at_the_same_time(fake_browser, monkeypatch):
    from agent_reach.runtime import browser

    real_launch = browser._launch

    def launch_while_daily_reconnects(url, *, headless=True):
        fake_browser["contexts"].remove("daily")  # the user's Chrome drops its Bridge connection ...
        real_launch(url, headless=headless)
        fake_browser["contexts"].insert(0, "daily")  # ... and reconnects while ours starts

    monkeypatch.setattr(browser, "_launch", launch_while_daily_reconnects)
    browser.setup()
    assert browser.bound_context() == "dedicated"


def test_wrong_record_is_repaired_before_a_query_uses_it(fake_browser):
    from agent_reach.runtime import browser

    browser.setup()
    browser.update_state(opencli_context="daily")  # e.g. written by an older Agent Reach
    browser.ensure_running()
    assert browser.bound_context() == "dedicated"


def test_windows_without_extension_still_needs_the_users_click(fake_browser, monkeypatch):
    from agent_reach.backends.opencli import OPENCLI_EXTENSION_URL, opencli_call
    from agent_reach.runtime import browser

    monkeypatch.setattr(browser, "can_load_extension", lambda: False)
    monkeypatch.setattr(browser, "_STORE_WAIT", 0.0)
    with pytest.raises(ReachError) as info:
        opencli_call("reddit", ["search", "x"], timeout=5)
    assert info.value.code == "NEED_SETUP"
    assert fake_browser["opened"] == [OPENCLI_EXTENSION_URL]
    assert browser.setup_problems()


def test_mac_and_linux_report_no_setup_problem_before_first_use(fake_browser):
    from agent_reach.runtime import browser

    assert browser.setup_problems() == []


def test_opencli_rebinds_once_when_the_owned_extension_disconnects(fake_browser, monkeypatch):
    from unittest.mock import Mock

    from agent_reach.backends.opencli import opencli_call
    from agent_reach.runtime import browser
    browser.setup()
    monkeypatch.setattr(browser, "watcher_running", lambda: fake_browser["watched"])
    fake_browser["contexts"].remove("dedicated")
    command = Mock(return_value="[]")
    monkeypatch.setattr("agent_reach.runtime.run.run_cmd", command)
    assert opencli_call("reddit", ["search", "x"], timeout=5) == []
    assert fake_browser["launches"] == 2 and command.call_count == 1
    assert browser.bound_context() == "dedicated"


def test_browser_left_open_without_watcher_is_reopened_with_extension(fake_browser, monkeypatch):
    from agent_reach.runtime import browser
    from agent_reach.runtime.browser_binding import environment

    browser.setup()
    fake_browser["contexts"].remove("dedicated")  # e.g. opened by an older Agent Reach, no extension
    monkeypatch.setattr(browser, "watcher_running", lambda: False)
    assert environment("reddit") ["OPENCLI_PROFILE"] == "dedicated"
    assert fake_browser["launches"] == 2


def test_login_opens_site_in_dedicated_browser(capsys, monkeypatch, fake_browser):
    class BrowserChannel(FakeChannel):
        name = "web2"
        login_url = "https://example.test/login"

    monkeypatch.setattr(unified, "get_all_channels", lambda: [BrowserChannel()])
    from agent_reach.runtime import manage
    added = []
    # Hermetic: no check of the real OpenCLI install on this machine.
    monkeypatch.setattr(manage, "add", lambda name, **k: added.append(name))
    code, out = _run(capsys, ["login", "web2"])
    assert code == 0
    assert added == ["web2"]
    assert fake_browser["opened"] == ["https://example.test/login"]


@pytest.mark.parametrize("argv", [["ask", "find VLA"], ["mcp"], ["cloak", "setup"], ["browser", "repair-opencli"],
                                  ["ensure", "xiaohongshu"],
                                  ["execute", "xiaohongshu", "search", "--params", '{"query":"VLA"}'],
                                  ["resume", "op_x"]])
def test_retired_commands_are_rejected_without_starting_any_service(argv, monkeypatch, capsys):
    from agent_reach.runtime import browser, manage
    monkeypatch.setattr(browser, "ensure_running", lambda *a, **k: pytest.fail("retired command started browser"))
    monkeypatch.setattr(manage, "add", lambda *a, **k: pytest.fail("retired command installed tools"))
    code, out = _run(capsys, argv)
    assert code == 1 and out["error"]["code"] == "BAD_INPUT"


@pytest.mark.parametrize(
    "yaml_text, code",
    [
        ("ok: false\nerror:\n  code: COMMAND_EXEC\n  message: 'Error: HTTP 401 - make sure you are logged in to Instagram'\n", "NEED_LOGIN"),
        ("ok: false\nerror:\n  code: AUTH_REQUIRED\n  message: 'Not logged into x.com'\n", "NEED_LOGIN"),
        ("ok: false\nerror:\n  code: COMMAND_EXEC\n  message: 'Pre-navigation to https://x.com failed: Navigation rejected.'\n", "UPSTREAM_BROKEN"),
        ("ok: false\nerror:\n  code: COMMAND_EXEC\n  message: 'TypeError: Failed to fetch'\n", "UPSTREAM_BROKEN"),
    ],
)
def test_opencli_errors_map_to_unified_codes(yaml_text, code):
    from agent_reach.backends.opencli import _opencli_error

    assert _opencli_error(yaml_text, "").code == code


def test_opencli_message_and_help_reach_the_agent_unchanged():
    from agent_reach.backends.opencli import _opencli_error
    from agent_reach.runtime.result import envelope

    text = ("node warning\nok: false\nerror:\n  code: BROWSER_CONNECT\n"
            "  message: Browser profile \"x\" is not connected\n  help: Open the matching Chrome profile.\n")
    err = _opencli_error(text, "reach login steps")
    out = envelope(channel="reddit", action="search", error=err)["error"]
    assert out == {"code": "UPSTREAM_BROKEN", "message": 'Browser profile "x" is not connected',
                   "hint": "Open the matching Chrome profile."}
    login = _opencli_error("ok: false\nerror:\n  code: AUTH_REQUIRED\n  message: Not logged into x.com\n"
                           "  help: Log in in your Chrome.\n", "reach login steps")
    assert login.message == "Not logged into x.com" and login.hint == "reach login steps"  # Reach's own browser



def test_query_uses_an_open_login_window_without_closing_it(fake_browser):
    from agent_reach.runtime import browser
    browser.setup()
    browser.update_state(headless=False)  # the user is logging in in a visible window
    browser.ensure_running()
    browser.setup()  # e.g. `agent-reach add` while the window is open
    assert browser._load_state()["headless"] is False
    assert fake_browser["running"] and fake_browser["launches"] == 1


def test_open_login_window_without_extension_is_busy_not_closed(fake_browser):
    from agent_reach.runtime import browser
    browser.setup()
    browser.update_state(headless=False)
    fake_browser["contexts"].remove("dedicated")
    with pytest.raises(ReachError) as info:
        browser.setup()
    assert info.value.code == "BUSY"
    assert fake_browser["running"] and fake_browser["launches"] == 1

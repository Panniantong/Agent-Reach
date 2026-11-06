"""Dispatch queues and paces only browser backends, never native ones in the same chain."""

import time
from contextlib import contextmanager

import pytest

from agent_reach.channels.base import Action, Channel
from agent_reach.runtime import dispatch
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import UPSTREAM_BROKEN, ReachError, make_item


class FakeChannel(Channel):
    name = "fake-routing"
    description = "dispatch routing probe"
    level = "optional"

    actions = (
        Action("native-only", "native only", (), (("native", "_native"),)),
        Action(
            "native-then-opencli",
            "native then opencli",
            (),
            (("native", "_broken_native"), ("opencli", "_opencli")),
        ),
        Action("slow", "sleeps briefly", (), (("native", "_slow"),)),
        Action("very-slow", "sleeps past the budget", (), (("native", "_very_slow"),)),
    )

    def __init__(self, events=None):
        self.events = events if events is not None else []

    def can_handle(self, url):
        return False

    def _native(self, *, timeout):
        return [make_item(title="native")]

    def _broken_native(self, *, timeout):
        self.events.append("native")
        raise ReachError(UPSTREAM_BROKEN, "native failed")

    def _opencli(self, *, timeout):
        return [make_item(title="opencli")]

    def _slow(self, *, timeout):
        time.sleep(0.4)
        return [make_item(title="slow")]

    def _very_slow(self, *, timeout):
        time.sleep(1.5)
        return [make_item(title="slow")]


def test_native_only_backend_never_takes_a_browser_slot_or_pacing(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("native-only backend must not touch the browser queue")

    monkeypatch.setattr(dispatch, "query_slot", forbidden)
    monkeypatch.setattr(dispatch, "_pace_browser", forbidden)

    result = run_action(FakeChannel(), "native-only", {})

    assert result["ok"]
    assert result["backend"] == "native"


def test_opencli_in_a_chain_takes_the_slot_and_pacing_exactly_once(monkeypatch):
    events = []

    @contextmanager
    def slot(site, clock=None):
        events.append("slot")
        yield

    monkeypatch.setattr(dispatch, "query_slot", slot)
    monkeypatch.setattr(dispatch, "_pace_browser", lambda *a: events.append("pace"))

    result = run_action(FakeChannel(events), "native-then-opencli", {})

    assert result["ok"]
    assert result["backend"] == "opencli"
    assert [row["backend"] for row in result["meta"]["attempts"]] == ["native", "opencli"]
    assert events == ["native", "slot", "pace"]


def test_cooldown_created_while_waiting_in_line_is_rechecked(monkeypatch):
    from agent_reach.runtime import state

    events = []
    channel = FakeChannel(events)

    @contextmanager
    def slot(site, clock=None):
        state.mutate(lambda data: data.setdefault("cooldowns", {}).__setitem__(
            channel.name,
            {"code": "RATE_LIMITED", "message": "limited", "at": state.now()},
        ))
        yield

    monkeypatch.setattr(dispatch, "query_slot", slot)
    monkeypatch.setattr(
        dispatch, "_pace_browser", lambda *a: pytest.fail("must stop before pacing")
    )

    result = run_action(channel, "native-then-opencli", {})

    assert result["error"]["code"] == "RATE_LIMITED"
    assert events == ["native"]  # opencli never ran


def test_slow_backend_succeeds_inside_a_large_budget():
    result = run_action(FakeChannel(), "slow", {}, timeout=5)
    assert result["ok"]
    assert result["items"][0]["title"] == "slow"


def test_slow_backend_times_out_when_the_budget_is_too_small():
    result = run_action(FakeChannel(), "very-slow", {}, timeout=0.1)
    assert not result["ok"]
    assert result["error"]["code"] == "TIMEOUT"

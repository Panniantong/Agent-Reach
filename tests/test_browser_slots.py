# -*- coding: utf-8 -*-
"""Parallel browser queries: per-site and overall slots, queueing, exclusive operations."""

import threading
import time

import pytest

from agent_reach.runtime import browser_binding as bb
from agent_reach.runtime.clock import Clock
from agent_reach.runtime.result import ReachError


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))


def _enter_later(fn):
    """Run `with fn():` in a thread; returns (entered event, release event, thread, errors)."""
    entered, release, errors = threading.Event(), threading.Event(), []

    def run():
        try:
            with fn():
                entered.set()
                release.wait(10)
        except ReachError as exc:
            errors.append(exc)

    t = threading.Thread(target=run)
    t.start()
    return entered, release, t, errors


def test_third_query_of_a_site_waits_in_line_while_other_sites_run(monkeypatch):
    with bb.query_slot("xiaohongshu"), bb.query_slot("xiaohongshu"):
        with bb.query_slot("twitter"):  # another site is not blocked by a full site
            pass
        entered, release, t, errors = _enter_later(lambda: bb.query_slot("xiaohongshu"))
        assert not entered.wait(0.6)  # queued, not refused
    assert entered.wait(5)
    release.set()
    t.join(5)
    assert errors == []


def test_queue_gives_up_with_busy_after_the_wait(monkeypatch):
    monkeypatch.setattr(bb, "QUEUE_WAIT", 0.3)
    with bb.query_slot("twitter"), bb.query_slot("twitter"):
        with pytest.raises(ReachError) as info:
            with bb.query_slot("twitter"):
                pass
    assert info.value.code == "BUSY"


def test_overall_limit_holds_across_sites(monkeypatch):
    monkeypatch.setattr(bb, "QUEUE_WAIT", 0.3)
    with bb.query_slot("a"), bb.query_slot("a"), bb.query_slot("b"), bb.query_slot("b"):
        with pytest.raises(ReachError):
            with bb.query_slot("c"):
                pass


def test_waiting_in_line_does_not_use_the_query_timeout():
    with bb.query_slot("x"), bb.query_slot("x"):
        clock = Clock(1.0)  # created once the line is full, so only the wait itself is measured
        entered, release, t, errors = _enter_later(lambda: bb.query_slot("x", clock))
        time.sleep(1.2)  # longer than the whole budget
    assert entered.wait(5)
    assert clock.remaining() > 0.3
    release.set()
    t.join(5)


def test_exclusive_waits_for_running_queries_and_holds_off_new_ones(monkeypatch):
    q_entered, q_release, q_thread, _ = _enter_later(lambda: bb.query_slot("twitter"))
    assert q_entered.wait(5)
    x_entered, x_release, x_thread, x_errors = _enter_later(bb.exclusive_browser)
    assert not x_entered.wait(0.5)  # a query is still running
    q_release.set()
    assert x_entered.wait(5)
    monkeypatch.setattr(bb, "QUEUE_WAIT", 0.3)
    with pytest.raises(ReachError):
        with bb.query_slot("xiaohongshu"):
            pass
    x_release.set()
    x_thread.join(5)
    q_thread.join(5)
    assert x_errors == []


def test_parallel_same_site_searches_stay_spaced(monkeypatch):
    from agent_reach.runtime import dispatch, state

    monkeypatch.setattr(dispatch, "BROWSER_SEARCH_INTERVAL", 0.8)
    stamps = []
    real_mutate = state.mutate

    def recording(change):
        def spy(saved):
            out = change(saved)
            starts = saved.get("request_starts", {})
            if "twitter" in starts:
                stamps.append(starts["twitter"])
            return out
        return real_mutate(spy)

    monkeypatch.setattr(dispatch.state, "mutate", recording)
    threads = [threading.Thread(target=lambda: dispatch._pace_browser("twitter", "search", Clock(10.0)))
               for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    starts = sorted(set(stamps))
    assert len(starts) == 2 and starts[1] - starts[0] >= 0.75  # the recorded search starts

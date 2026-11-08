# -*- coding: utf-8 -*-
"""Live checks: a deleted live_test sample is stale evidence, not a broken channel.

When every backend of an action's live test answers NOT_FOUND, the sample
itself is gone (e.g. the fixture video was deleted upstream); the capability
was never tested. `run_checks` marks those rows "stale", keeps them
unverified, and does not fail the check or flip the channel to broken.
Genuine failures (any other code, or a mix) still fail as before.
"""

import json

import pytest

from agent_reach.channels import bilibili
from agent_reach.channels.base import Action, Channel, Param
from agent_reach.runtime import cli, manage, tools
from agent_reach.runtime.result import NEED_LOGIN, NOT_FOUND, UPSTREAM_BROKEN, ReachError
from agent_reach.runtime.run import CommandFailed


class _Base(Channel):
    description = "x"
    level = "optional"

    def can_handle(self, url):
        return False

    def _ok(self, **kw):
        return [{"title": "ok"}]

    def _gone(self, **kw):
        raise ReachError(NOT_FOUND, "video not found")

    def _sick(self, **kw):
        raise ReachError(UPSTREAM_BROKEN, "returned unreadable output")

    def _login(self, **kw):
        raise ReachError(NEED_LOGIN, "not logged in")


class Gone(_Base):
    """search healthy; the read/subtitle live_test samples were deleted upstream.

    `sample_alive` lets a test delete the sample between two checks.
    """

    name = "gone"
    sample_alive = True
    actions = (
        Action("search", "s", (Param("query", "q"),), (("b", "_ok"),), live_test={"query": "x"}),
        Action("read", "r", (Param("target", "t"),),
               (("b1", "_sample"), ("b2", "_sample")), live_test={"target": "BVgone"}),
        Action("subtitle", "st", (Param("target", "t"),), (("b1", "_sample"),), live_test={"target": "BVgone"}),
    )

    def _sample(self, **kw):
        if type(self).sample_alive:
            return [{"title": "ok"}]
        raise ReachError(NOT_FOUND, "video not found")


class Sick(_Base):
    """read genuinely broken: upstream returns unreadable output for any target."""

    name = "sick"
    actions = (
        Action("read", "r", (Param("target", "t"),), (("b1", "_sick"),), live_test={"target": "BVx"}),
    )


class Mixed(_Base):
    """one backend says the sample is gone, the other is genuinely broken."""

    name = "mixed"
    actions = (
        Action("read", "r", (Param("target", "t"),),
               (("b1", "_gone"), ("b2", "_sick")), live_test={"target": "BVx"}),
    )


class GoneAndLogin(_Base):
    """read's sample is gone and subtitle honestly needs a login."""

    name = "gonelogin"
    actions = (
        Action("read", "r", (Param("target", "t"),), (("b1", "_gone"),), live_test={"target": "BVgone"}),
        Action("subtitle", "st", (Param("target", "t"),), (("b1", "_login"),), live_test={"target": "BVx"}),
    )


@pytest.fixture
def chans(monkeypatch):
    Gone.sample_alive = True
    cs = [Gone(), Sick(), Mixed(), GoneAndLogin()]
    monkeypatch.setattr(manage, "_channels", lambda: cs)
    return cs


def _doctor(name):
    return next(c for c in manage.doctor()["channels"] if c["channel"] == name)


def _rows(out, channel, action):
    return [r for r in out["results"] if r["channel"] == channel and r["action"] == action]


def test_stale_sample_does_not_fail_check_or_break_channel(chans):
    manage.add("gone")
    Gone.sample_alive = False
    out = manage.run_checks(["gone"])
    assert out["ok"] is True
    for action in ("read", "subtitle"):
        rows = _rows(out, "gone", action)
        assert rows and all(r["passed"] is False and r["stale"] is True for r in rows)
        assert all(r["error"]["code"] == NOT_FOUND for r in rows)
    assert all("stale" not in r for r in _rows(out, "gone", "search"))
    status = _doctor("gone")
    assert status["status"] == "ready"
    assert status["problems"] == []
    assert status["verified_actions"] == ["search"], "stale actions stay unverified, not passed"


def test_deleted_sample_is_not_a_regression(chans):
    manage.add("gone")
    manage.run_checks(["gone"])
    assert _doctor("gone")["regressed"] is False
    Gone.sample_alive = False
    manage.run_checks(["gone"])
    status = _doctor("gone")
    assert status["status"] == "ready"
    assert status["regressed"] is False, "a deleted sample must not read as a capability regression"


def test_genuine_failure_still_broken(chans):
    manage.add("sick")
    out = manage.run_checks(["sick"])
    assert out["ok"] is False
    assert all("stale" not in r for r in out["results"])
    assert _doctor("sick")["status"] == "broken"


def test_mixed_not_found_and_genuine_failure_still_broken(chans):
    manage.add("mixed")
    out = manage.run_checks(["mixed"])
    assert out["ok"] is False
    assert all("stale" not in r for r in out["results"])
    assert _doctor("mixed")["status"] == "broken"


def test_stale_does_not_swallow_a_login_failure(chans):
    manage.add("gonelogin")
    out = manage.run_checks(["gonelogin"])
    assert out["ok"] is False, "the NEED_LOGIN action is a real failure of the check run"
    assert all(r.get("stale") is True for r in _rows(out, "gonelogin", "read"))
    assert _doctor("gonelogin")["status"] == "needs_login"


def test_check_text_marks_stale_rows_and_exits_zero(chans, capsys):
    manage.add("gone")
    Gone.sample_alive = False
    assert cli.main(["check", "gone", "--text"]) == 0
    text = capsys.readouterr().out
    assert "STALE  gone read" in text
    assert "STALE  gone subtitle" in text
    assert "1/3 actions working; 2 skipped (live sample no longer exists)" in text


# ── the reported scenario, end to end on the real Bilibili channel ──

_DELETED = "BV1GJ411x7h7"


def _fake_run_cmd(argv, timeout=None, env=None, input_data=None, label=None):
    args = [a for a in argv if a != "--json"]
    if args[1] == "search":
        return json.dumps({"ok": True, "data": [{"title": "s", "bvid": "BV1xx", "owner": {"name": "u"}}]})
    if args[1] == "hot":
        return json.dumps({"ok": True, "data": {"items": [{"title": "h", "bvid": "BV1yy", "owner": {"name": "u"}}]}})
    if args[1] == "video" and _DELETED in args:
        raise CommandFailed("UPSTREAM_BROKEN", "bili exited 1", stdout=json.dumps(
            {"ok": False, "error": {"code": "not_found", "message": "video not found"}}))
    raise AssertionError(f"unexpected bili argv: {argv}")


def _fake_http_request(url, timeout=None, headers=None):
    if "view?bvid=" in url and _DELETED in url:
        return json.dumps({"code": -404, "message": "啥都木有"})
    if "popular" in url:
        return json.dumps({"code": 0, "data": {"list": [{"title": "h", "bvid": "BV1yy", "owner": {"name": "u"}}]}})
    raise AssertionError(f"unexpected url: {url}")


@pytest.fixture
def real_bilibili(monkeypatch):
    monkeypatch.setattr(bilibili, "run_cmd", _fake_run_cmd)
    monkeypatch.setattr(bilibili, "http_request", _fake_http_request)
    monkeypatch.setattr(bilibili, "_reuse_subtitle_login", lambda timeout: None)
    monkeypatch.setattr(tools, "present", lambda name, data=None: True)
    monkeypatch.setattr(manage, "_channels", lambda: [bilibili.BilibiliChannel()])


def test_bilibili_deleted_fixture_is_stale_not_broken(real_bilibili):
    out = manage.run_checks(["bilibili"])
    assert out["ok"] is True
    for action in ("read", "subtitle"):
        rows = _rows(out, "bilibili", action)
        assert rows and all(r["stale"] is True and r["error"]["code"] == NOT_FOUND for r in rows)
    status = _doctor("bilibili")
    assert status["status"] == "ready"
    assert set(status["verified_actions"]) == {"search", "hot"}

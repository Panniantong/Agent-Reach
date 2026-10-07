# -*- coding: utf-8 -*-

import json
import time

import pytest

from agent_reach.backends import OpenCLIStatus, opencli_live
from agent_reach.channels.facebook import FacebookChannel
from agent_reach.channels.instagram import InstagramChannel
from agent_reach.channels.reddit import RedditChannel
from agent_reach.channels.twitter import TwitterChannel
from agent_reach.config import Config
from agent_reach.probe import ProbeResult


@pytest.fixture
def bridge_ready(monkeypatch):
    monkeypatch.setattr(
        "agent_reach.backends.opencli_status",
        lambda: OpenCLIStatus(installed=True, extension_connected=True, version="1.8.8"),
    )


@pytest.fixture
def probe_calls(monkeypatch):
    calls = []
    outputs = {}

    def fake_probe(cmd, args=(), timeout=10, **kwargs):
        calls.append((cmd, tuple(args)))
        return outputs.get(args[0], ProbeResult("ok", output="[]"))

    monkeypatch.setattr(opencli_live, "probe_command", fake_probe)
    return calls, outputs


def test_live_off_by_default_keeps_unverified_warn(
    monkeypatch, isolated_home, bridge_ready, probe_calls
):
    monkeypatch.delenv(opencli_live.LIVE_ENV, raising=False)
    calls, _ = probe_calls

    status, msg = FacebookChannel().check()

    assert status == "warn"
    assert "未实时验证" in msg
    assert calls == []


def test_live_success_marks_site_channel_ok(monkeypatch, isolated_home, bridge_ready, probe_calls):
    monkeypatch.setenv(opencli_live.LIVE_ENV, "1")
    calls, _ = probe_calls

    ch = FacebookChannel()
    status, msg = ch.check()

    assert status == "ok"
    assert ch.active_backend == "OpenCLI"
    assert "实时验证通过" in msg
    assert calls == [("opencli", ("facebook", "profile", "zuck", "-f", "json"))]


def test_live_failure_stays_warn_with_reason(monkeypatch, isolated_home, bridge_ready, probe_calls):
    monkeypatch.setenv(opencli_live.LIVE_ENV, "1")
    _, outputs = probe_calls
    outputs["instagram"] = ProbeResult("error", output="Error: HTTP 429")

    ch = InstagramChannel()
    status, msg = ch.check()

    assert status == "warn"
    assert ch.active_backend is None
    assert "HTTP 429" in msg


def test_handled_opencli_error_in_output_is_not_success(
    monkeypatch, isolated_home, bridge_ready, probe_calls
):
    monkeypatch.setenv(opencli_live.LIVE_ENV, "1")
    _, outputs = probe_calls
    outputs["facebook"] = ProbeResult("ok", output='{"ok": false, "error": {}}')

    status, _ = FacebookChannel().check()

    assert status == "warn"


def test_reddit_and_twitter_use_opencli_when_verified(
    monkeypatch, isolated_home, bridge_ready, probe_calls
):
    monkeypatch.setenv(opencli_live.LIVE_ENV, "1")
    monkeypatch.setattr(
        "shutil.which", lambda cmd: "/usr/bin/opencli" if cmd == "opencli" else None
    )
    _, outputs = probe_calls
    outputs["twitter"] = ProbeResult("ok", output='[{"logged_in": true}]')

    reddit = RedditChannel()
    assert reddit.check()[0] == "ok"
    assert reddit.active_backend == "OpenCLI"

    twitter = TwitterChannel()
    assert twitter.check()[0] == "ok"
    assert twitter.active_backend == "OpenCLI"


def test_twitter_requires_logged_in(monkeypatch, isolated_home, bridge_ready, probe_calls):
    monkeypatch.setenv(opencli_live.LIVE_ENV, "1")
    monkeypatch.setattr(
        "shutil.which", lambda cmd: "/usr/bin/opencli" if cmd == "opencli" else None
    )
    _, outputs = probe_calls
    outputs["twitter"] = ProbeResult("ok", output='[{"logged_in": false}]')

    assert TwitterChannel().check()[0] == "warn"


def test_results_are_cached(monkeypatch, isolated_home, bridge_ready, probe_calls):
    monkeypatch.setenv(opencli_live.LIVE_ENV, "1")
    calls, _ = probe_calls

    FacebookChannel().check()
    status, msg = FacebookChannel().check()

    assert status == "ok"
    assert len(calls) == 1
    assert "缓存" in msg
    cache_file = Config.CONFIG_DIR / "live-check.json"
    assert json.loads(cache_file.read_text())["facebook"]["ok"] is True


def test_failed_results_expire_sooner(monkeypatch, isolated_home, bridge_ready, probe_calls):
    monkeypatch.setenv(opencli_live.LIVE_ENV, "1")
    calls, _ = probe_calls
    stale = time.time() - opencli_live.LIVE_FAIL_TTL_SECONDS - 1
    opencli_live._write_cache({"facebook": {"ok": False, "at": stale, "detail": "x"}})

    status, _ = FacebookChannel().check()

    assert status == "ok"
    assert len(calls) == 1


def test_probes_are_read_only():
    write_commands = {
        "post",
        "reply",
        "delete",
        "like",
        "follow",
        "retweet",
        "quote",
        "block",
        "reply-dm",
        "bookmark",
        "accept",
    }
    for args in opencli_live._LIVE_PROBES.values():
        assert args[1] not in write_commands

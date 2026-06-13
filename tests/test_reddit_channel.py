# -*- coding: utf-8 -*-
"""Dedicated tests for the ``reddit`` channel.

Reddit is a tier-1, multi-backend channel (OpenCLI → rdt-cli) with no
zero-config path, so its ``check`` has the richest branching of the text
channels: per-backend probing, ok/warn/error/off precedence, and a
hand-rolled ``rdt status --json`` parse that must map every subprocess
outcome onto the probe vocabulary. Follow-up to #331 — completes dedicated
coverage after rss (#360), github (#361) and web (#363).
"""

from unittest.mock import Mock, patch

from agent_reach.channels.reddit import RedditChannel


def _cp(stdout="", stderr="", returncode=0):
    m = Mock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = returncode
    return m


# --- can_handle ---

def test_can_handle_matches_reddit_hosts():
    ch = RedditChannel()
    for url in [
        "https://reddit.com/r/python",
        "https://www.reddit.com/r/python/comments/abc/title/",
        "https://old.reddit.com/r/python",
        "https://redd.it/abc123",
        "HTTPS://REDDIT.COM/r/Python",  # case-insensitive netloc
    ]:
        assert ch.can_handle(url) is True, url


def test_can_handle_rejects_non_reddit():
    ch = RedditChannel()
    # Matching is netloc-substring based (the codebase-wide convention), so
    # use hosts that genuinely don't contain the reddit markers.
    for url in ["https://example.com/r/python", "https://twitter.com/u", ""]:
        assert ch.can_handle(url) is False, url


# --- _check_rdt: map every subprocess outcome onto the probe vocabulary ---

def test_check_rdt_returns_none_when_not_installed():
    ch = RedditChannel()
    with patch("shutil.which", return_value=None):
        assert ch._check_rdt() is None


def test_check_rdt_authenticated_with_username_is_ok():
    ch = RedditChannel()
    payload = '{"data": {"authenticated": true, "username": "alice"}}'
    with patch("shutil.which", return_value="/usr/local/bin/rdt"), patch(
        "subprocess.run", return_value=_cp(stdout=payload, returncode=0)
    ):
        status, message = ch._check_rdt()
    assert status == "ok"
    assert "alice" in message


def test_check_rdt_authenticated_without_username_is_ok_no_suffix():
    ch = RedditChannel()
    payload = '{"data": {"authenticated": true}}'
    with patch("shutil.which", return_value="/usr/local/bin/rdt"), patch(
        "subprocess.run", return_value=_cp(stdout=payload, returncode=0)
    ):
        status, message = ch._check_rdt()
    assert status == "ok"
    assert "已登录" not in message


def test_check_rdt_not_authenticated_is_warn():
    ch = RedditChannel()
    payload = '{"data": {"authenticated": false}}'
    with patch("shutil.which", return_value="/usr/local/bin/rdt"), patch(
        "subprocess.run", return_value=_cp(stdout=payload, returncode=0)
    ):
        status, message = ch._check_rdt()
    assert status == "warn"
    assert "未登录" in message


def test_check_rdt_unparseable_status_is_warn():
    ch = RedditChannel()
    with patch("shutil.which", return_value="/usr/local/bin/rdt"), patch(
        "subprocess.run", return_value=_cp(stdout="not json", returncode=0)
    ):
        status, message = ch._check_rdt()
    assert status == "warn"
    assert "无法解析" in message


def test_check_rdt_broken_exit_code_is_error_with_venv_hint():
    ch = RedditChannel()
    with patch("shutil.which", return_value="/usr/local/bin/rdt"), patch(
        "subprocess.run", return_value=_cp(stderr="", returncode=127)
    ):
        status, message = ch._check_rdt()
    assert status == "error"
    assert "强制重装" in message  # the venv-relink prescription


def test_check_rdt_nonzero_exit_reports_tail():
    ch = RedditChannel()
    with patch("shutil.which", return_value="/usr/local/bin/rdt"), patch(
        "subprocess.run", return_value=_cp(stderr="boom: network down", returncode=1)
    ):
        status, message = ch._check_rdt()
    assert status == "error"
    assert "exit 1" in message
    assert "boom: network down" in message


def test_check_rdt_timeout_is_error():
    import subprocess
    ch = RedditChannel()
    with patch("shutil.which", return_value="/usr/local/bin/rdt"), patch(
        "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="rdt", timeout=10)
    ):
        status, message = ch._check_rdt()
    assert status == "error"
    assert "超时" in message


def test_check_rdt_oserror_is_broken():
    ch = RedditChannel()
    with patch("shutil.which", return_value="/usr/local/bin/rdt"), patch(
        "subprocess.run", side_effect=OSError("exec format error")
    ):
        status, message = ch._check_rdt()
    assert status == "error"
    assert "强制重装" in message


# --- _check_opencli: maps OpenCLIStatus onto the probe vocabulary ---

def _opencli(installed=True, broken=False, ready=True, hint=""):
    return Mock(installed=installed, broken=broken, ready=ready, hint=hint)


def test_check_opencli_not_installed_is_none():
    ch = RedditChannel()
    with patch("agent_reach.backends.opencli_status", return_value=_opencli(installed=False)):
        assert ch._check_opencli() is None


def test_check_opencli_broken_is_error():
    ch = RedditChannel()
    with patch("agent_reach.backends.opencli_status",
               return_value=_opencli(broken=True, hint="reinstall opencli")):
        status, message = ch._check_opencli()
    assert status == "error"
    assert message == "reinstall opencli"


def test_check_opencli_ready_is_ok():
    ch = RedditChannel()
    with patch("agent_reach.backends.opencli_status", return_value=_opencli(ready=True)):
        status, message = ch._check_opencli()
    assert status == "ok"
    assert "OpenCLI" in message


def test_check_opencli_installed_not_ready_is_warn():
    ch = RedditChannel()
    with patch("agent_reach.backends.opencli_status",
               return_value=_opencli(ready=False, hint="connect the extension")):
        status, message = ch._check_opencli()
    assert status == "warn"
    assert message == "connect the extension"


# --- check(): precedence across backends + active_backend selection ---

def test_check_prefers_ok_over_warn_regardless_of_probe_order():
    # OpenCLI probes first and only warns; rdt-cli is fully ok. The ok
    # backend must win and become active even though it was probed second.
    ch = RedditChannel()
    with patch.object(ch, "_check_opencli", return_value=("warn", "opencli sleepy")), \
         patch.object(ch, "_check_rdt", return_value=("ok", "rdt ready")):
        status, message = ch.check()
    assert status == "ok"
    assert message == "rdt ready"
    assert ch.active_backend == "rdt-cli"


def test_check_first_ok_backend_becomes_active():
    ch = RedditChannel()
    with patch.object(ch, "_check_opencli", return_value=("ok", "opencli ready")), \
         patch.object(ch, "_check_rdt", return_value=("warn", "rdt not logged in")):
        status, _ = ch.check()
    assert status == "ok"
    assert ch.active_backend == "OpenCLI"


def test_check_all_errors_returns_error_and_no_active_backend():
    ch = RedditChannel()
    with patch.object(ch, "_check_opencli", return_value=("error", "e1")), \
         patch.object(ch, "_check_rdt", return_value=("error", "e2")):
        status, message = ch.check()
    assert status == "error"
    assert "e1" in message and "e2" in message
    assert ch.active_backend is None


def test_check_no_backend_installed_is_off():
    ch = RedditChannel()
    with patch.object(ch, "_check_opencli", return_value=None), \
         patch.object(ch, "_check_rdt", return_value=None):
        status, message = ch.check()
    assert status == "off"
    assert "零配置" in message  # "no zero-config path" guidance
    assert ch.active_backend is None

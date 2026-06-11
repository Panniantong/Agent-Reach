# -*- coding: utf-8 -*-
"""Tests for the OpenCLI cross-channel backend probing."""

from unittest.mock import patch

from agent_reach.backends import opencli_status, opencli_summary
from agent_reach.probe import ProbeResult


def _status_with(version_probe, daemon_probe=None, ext_on_disk=False):
    """Run opencli_status with probe_command and disk check patched."""
    calls = []

    def fake_probe(cmd, args=("--version",), **kwargs):
        calls.append(list(args))
        if list(args) == ["--version"]:
            return version_probe
        return daemon_probe or ProbeResult("missing")

    with patch("agent_reach.backends.opencli.probe_command", side_effect=fake_probe), \
         patch(
             "agent_reach.backends.opencli._extension_installed_on_disk",
             return_value=ext_on_disk,
         ):
        return opencli_status(), calls


def test_not_installed():
    st, _ = _status_with(ProbeResult("missing"))
    assert not st.installed
    assert not st.ready
    assert "未安装" in opencli_summary(st)


def test_broken_node_env_gives_npm_hint():
    st, _ = _status_with(ProbeResult("broken", hint="x"))
    assert st.installed and st.broken
    assert "npm install -g @jackwener/opencli" in st.hint
    assert not st.ready


def test_daemon_running_extension_connected_is_ready():
    daemon_out = "Daemon: running (PID 37389)\nVersion: v1.8.3\nExtension: connected\n"
    st, _ = _status_with(
        ProbeResult("ok", output="1.8.3"),
        ProbeResult("ok", output=daemon_out),
    )
    assert st.installed and st.daemon_running and st.extension_connected
    assert st.ready
    assert "1.8.3" in opencli_summary(st)


def test_extension_never_installed_not_ready_with_store_guide():
    daemon_out = "Daemon: running (PID 1)\nExtension: disconnected\n"
    st, _ = _status_with(
        ProbeResult("ok", output="1.8.3"),
        ProbeResult("ok", output=daemon_out),
        ext_on_disk=False,
    )
    assert st.daemon_running and not st.extension_connected
    assert not st.ready
    assert "chromewebstore.google.com" in st.hint


def test_sleeping_extension_counts_as_ready():
    """实测:扩展 service worker 睡眠时 daemon status 报 disconnected,
    但任何真实命令会唤醒它——装在磁盘上即视为可用。"""
    daemon_out = "Daemon: running (PID 1)\nExtension: disconnected\n"
    st, _ = _status_with(
        ProbeResult("ok", output="1.8.3"),
        ProbeResult("ok", output=daemon_out),
        ext_on_disk=True,
    )
    assert not st.extension_connected
    assert st.extension_installed
    assert st.ready
    assert "唤醒" in opencli_summary(st)
    assert st.hint == ""


def test_daemon_not_running_parsed_correctly():
    st, _ = _status_with(
        ProbeResult("ok", output="1.8.3"),
        ProbeResult("ok", output="Daemon: not running\n"),
    )
    assert st.installed
    assert not st.daemon_running
    assert not st.extension_connected
    assert "自动启动" in opencli_summary(st)


def test_probe_uses_daemon_status_not_doctor():
    """`opencli doctor` auto-starts the daemon (side effect) — health checks
    must only ever call `daemon status`."""
    _, calls = _status_with(
        ProbeResult("ok", output="1.8.3"),
        ProbeResult("ok", output="Daemon: not running\n"),
    )
    assert ["daemon", "status"] in calls
    assert ["doctor"] not in calls

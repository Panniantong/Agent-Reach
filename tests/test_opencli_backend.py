# -*- coding: utf-8 -*-
"""Tests for the OpenCLI cross-channel backend probing."""

from unittest.mock import patch

from agent_reach.backends import opencli_status, opencli_summary
from agent_reach.backends.opencli import (
    OPENCLI_EXTENSION_ID,
    _extension_installed_on_disk,
    _unpacked_extension_files_present,
)
from agent_reach.probe import ProbeResult


def _status_with(
    version_probe,
    daemon_status=None,
    ext_on_disk=False,
    unpacked_files=False,
):
    """Run opencli_status with the CLI version and HTTP status patched."""
    calls = []

    def fake_probe(cmd, args=("--version",), **kwargs):
        calls.append(list(args))
        return version_probe

    with patch("agent_reach.backends.opencli.probe_command", side_effect=fake_probe), \
         patch(
             "agent_reach.backends.opencli._fetch_daemon_status",
             return_value=daemon_status,
         ), \
         patch(
             "agent_reach.backends.opencli._extension_installed_on_disk",
             return_value=ext_on_disk,
         ), \
         patch(
             "agent_reach.backends.opencli._unpacked_extension_files_present",
             return_value=unpacked_files,
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
    daemon_status = {
        "ok": True,
        "pid": 37389,
        "extensionConnected": True,
    }
    st, _ = _status_with(
        ProbeResult("ok", output="1.8.3"),
        daemon_status,
    )
    assert st.installed and st.daemon_running and st.extension_connected
    assert st.ready
    assert "1.8.3" in opencli_summary(st)


def test_extension_never_installed_not_ready_with_store_guide():
    daemon_status = {"ok": True, "pid": 1, "extensionConnected": False}
    st, _ = _status_with(
        ProbeResult("ok", output="1.8.3"),
        daemon_status,
        ext_on_disk=False,
    )
    assert st.daemon_running and not st.extension_connected
    assert not st.ready
    assert "chromewebstore.google.com" in st.hint


def test_extension_files_on_disk_are_not_reported_as_loaded_or_ready():
    """A disabled/stale extension leaves files behind, so disk != loaded."""
    daemon_status = {"ok": True, "pid": 1, "extensionConnected": False}
    st, _ = _status_with(
        ProbeResult("ok", output="1.8.3"),
        daemon_status,
        ext_on_disk=True,
    )
    assert not st.extension_connected
    assert st.extension_installed
    assert not st.ready
    assert "可用" not in opencli_summary(st)
    assert "无法确认" in st.hint


def test_unpacked_source_files_are_not_reported_as_loaded_or_ready():
    daemon_status = {"ok": True, "pid": 1, "extensionConnected": False}
    st, _ = _status_with(
        ProbeResult("ok", output="1.8.3"),
        daemon_status,
        unpacked_files=True,
    )
    assert st.unpacked_extension_files
    assert not st.extension_connected
    assert not st.ready
    assert "不代表" in st.hint
    assert "可用" not in opencli_summary(st)


def test_daemon_not_running_parsed_correctly():
    st, _ = _status_with(
        ProbeResult("ok", output="1.8.3"),
        None,
    )
    assert st.installed
    assert not st.daemon_running
    assert not st.extension_connected
    assert "自动启动" in opencli_summary(st)


def test_probe_never_executes_any_daemon_or_doctor_command():
    """Even `daemon status` mutates ~/.opencli in current upstream releases."""
    _, calls = _status_with(
        ProbeResult("ok", output="1.8.3"),
        None,
    )
    assert calls == [["--version"]]


def test_opencli_probes_strip_deprecated_app_env_only_from_children(monkeypatch):
    """OpenCLIApp can inject a variable that makes every CLI command exit 78.

    Agent Reach must remove it from both read-only child probes without
    mutating the desktop app's parent environment.
    """
    monkeypatch.setenv("OPENCLI_DAEMON_PORT", "19825")
    calls = []

    def fake_probe(cmd, args=("--version",), **kwargs):
        calls.append((list(args), tuple(kwargs.get("remove_env", ()))))
        if "OPENCLI_DAEMON_PORT" not in kwargs.get("remove_env", ()):
            return ProbeResult(
                "error",
                output="OPENCLI_DAEMON_PORT is no longer supported",
            )
        return ProbeResult("ok", output="1.8.6")

    with patch("agent_reach.backends.opencli.probe_command", side_effect=fake_probe), patch(
        "agent_reach.backends.opencli._fetch_daemon_status",
        return_value=None,
    ), patch(
        "agent_reach.backends.opencli._extension_installed_on_disk",
        return_value=False,
    ):
        status = opencli_status()

    assert status.installed and not status.broken
    assert calls == [
        (["--version"], ("OPENCLI_DAEMON_PORT",)),
    ]
    assert "OPENCLI_DAEMON_PORT" in __import__("os").environ


def test_store_install_scan_includes_edge_profiles(tmp_path, monkeypatch):
    edge_root = tmp_path / "Microsoft Edge"
    (
        edge_root
        / "Default"
        / "Extensions"
        / OPENCLI_EXTENSION_ID
        / "1.0.0"
    ).mkdir(parents=True)

    monkeypatch.setattr(
        "agent_reach.backends.opencli._CHROME_PROFILE_ROOTS",
        (str(edge_root),),
    )
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert _extension_installed_on_disk()


def test_unpacked_scan_requires_manifest_but_does_not_claim_browser_load(
    tmp_path, monkeypatch
):
    unpacked = tmp_path / ".opencli" / "extension"
    unpacked.mkdir(parents=True)
    monkeypatch.setattr(
        "agent_reach.backends.opencli._OPENCLI_UNPACKED_EXTENSION",
        str(unpacked),
    )

    assert not _unpacked_extension_files_present()
    (unpacked / "manifest.json").write_text('{"name": "OpenCLI"}', encoding="utf-8")
    assert _unpacked_extension_files_present()

# -*- coding: utf-8 -*-
"""Tests for agent_reach.probe — real-execution probing and failure classification."""

import os
import stat
import sys

import pytest

from agent_reach.probe import probe_command, reinstall_hint


def _make_executable(path, content):
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


def test_missing_command():
    r = probe_command("definitely-not-a-real-command-xyz")
    assert r.status == "missing"
    assert not r.ok


@pytest.mark.skipif(sys.platform == "win32", reason="shebang semantics are POSIX-only")
def test_broken_shebang_detected_as_broken(tmp_path, monkeypatch):
    """A stale venv shim: which() finds it, exec raises FileNotFoundError."""
    _make_executable(
        tmp_path / "stale-tool", "#!/nonexistent/venv/bin/python\nprint('hi')\n"
    )
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))

    r = probe_command("stale-tool", package="stale-tool-pkg")
    assert r.status == "broken"
    assert "uv tool install --force stale-tool-pkg" in r.hint
    assert "pipx reinstall stale-tool-pkg" in r.hint


@pytest.mark.skipif(sys.platform == "win32", reason="shell script fixture is POSIX-only")
def test_healthy_command_returns_ok_with_output(tmp_path, monkeypatch):
    _make_executable(
        tmp_path / "healthy-tool", "#!/bin/sh\necho 'healthy-tool 1.2.3'\n"
    )
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))

    r = probe_command("healthy-tool")
    assert r.ok
    assert "1.2.3" in r.output


@pytest.mark.skipif(sys.platform == "win32", reason="shell script fixture is POSIX-only")
def test_nonzero_exit_classified_as_error(tmp_path, monkeypatch):
    _make_executable(
        tmp_path / "failing-tool", "#!/bin/sh\necho 'boom' >&2\nexit 3\n"
    )
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))

    r = probe_command("failing-tool")
    assert r.status == "error"
    assert "boom" in r.output


@pytest.mark.skipif(sys.platform == "win32", reason="shell script fixture is POSIX-only")
def test_exit_127_classified_as_broken(tmp_path, monkeypatch):
    _make_executable(tmp_path / "wrapper-tool", "#!/bin/sh\nexit 127\n")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))

    r = probe_command("wrapper-tool", package="wrapper-pkg")
    assert r.status == "broken"
    assert "wrapper-pkg" in r.hint


@pytest.mark.skipif(sys.platform == "win32", reason="shell script fixture is POSIX-only")
def test_retries_help_transient_failures(tmp_path, monkeypatch):
    """First call fails (exit 1), second succeeds — retries=1 should return ok."""
    marker = tmp_path / "ran-once"
    _make_executable(
        tmp_path / "flaky-tool",
        f"#!/bin/sh\nif [ -f {marker} ]; then echo ok; exit 0; fi\ntouch {marker}\nexit 1\n",
    )
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))

    r = probe_command("flaky-tool", retries=1)
    assert r.ok


def test_reinstall_hint_mentions_both_installers():
    hint = reinstall_hint("some-pkg")
    assert "uv tool install --force some-pkg" in hint
    assert "pipx reinstall some-pkg" in hint

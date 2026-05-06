# -*- coding: utf-8 -*-
"""Tests for hivereach._install_helpers."""

from unittest.mock import patch

import pytest

from hivereach._install_helpers import install_pipx_tool


@pytest.fixture
def fake_subprocess(monkeypatch):
    calls = []

    def _run(cmd, **kwargs):
        calls.append(cmd)

    monkeypatch.setattr("hivereach._install_helpers.subprocess.run", _run)
    return calls


def test_already_installed_short_circuits(fake_subprocess, capsys):
    with patch("hivereach._install_helpers.shutil.which", return_value="/usr/bin/twitter"):
        install_pipx_tool(
            label="Twitter (twitter-cli)",
            binary="twitter",
            package="twitter-cli",
        )

    out = capsys.readouterr().out
    assert "Setting up Twitter (twitter-cli)..." in out
    assert "✅ twitter-cli already installed" in out
    assert fake_subprocess == []


def test_pipx_install_succeeds(fake_subprocess, capsys):
    """First which() call (binary): None. Second (pipx): truthy. Third (binary again): truthy."""
    with patch(
        "hivereach._install_helpers.shutil.which",
        side_effect=[None, "/usr/bin/pipx", "/usr/bin/twitter"],
    ):
        install_pipx_tool(
            label="Twitter (twitter-cli)",
            binary="twitter",
            package="twitter-cli",
        )

    out = capsys.readouterr().out
    assert "✅ twitter-cli installed" in out
    assert "(" not in out.split("installed")[1].split("\n")[0]  # no hint suffix
    assert fake_subprocess == [["pipx", "install", "twitter-cli"]]


def test_post_install_hint_renders(fake_subprocess, capsys):
    with patch(
        "hivereach._install_helpers.shutil.which",
        side_effect=[None, "/usr/bin/pipx", "/usr/bin/xhs"],
    ):
        install_pipx_tool(
            label="XiaoHongShu (xhs-cli)",
            binary="xhs",
            package="xiaohongshu-cli",
            post_install_hint="run `xhs login` to authenticate",
        )

    out = capsys.readouterr().out
    assert "✅ xiaohongshu-cli installed (run `xhs login` to authenticate)" in out


def test_falls_back_to_uv_when_pipx_missing(fake_subprocess, capsys):
    """binary missing → pipx missing → uv present → install via uv → binary appears."""
    with patch(
        "hivereach._install_helpers.shutil.which",
        side_effect=[None, None, "/usr/bin/uv", "/usr/bin/rdt"],
    ):
        install_pipx_tool(
            label="Reddit (rdt-cli)",
            binary="rdt",
            package="rdt-cli",
        )

    assert fake_subprocess == [["uv", "tool", "install", "rdt-cli"]]
    assert "✅ rdt-cli installed" in capsys.readouterr().out


def test_no_installer_prints_manual_hint(fake_subprocess, capsys):
    """No binary, no pipx, no uv → print manual recovery hint."""
    with patch("hivereach._install_helpers.shutil.which", return_value=None):
        install_pipx_tool(
            label="Reddit (rdt-cli)",
            binary="rdt",
            package="rdt-cli",
        )

    assert fake_subprocess == []
    assert "[!]  rdt-cli install failed. Run: pipx install rdt-cli" in capsys.readouterr().out


def test_subprocess_error_is_swallowed_and_falls_through(monkeypatch, capsys):
    import subprocess as _sp

    calls = []

    def _run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "pipx":
            raise _sp.TimeoutExpired(cmd, 1)
        # uv "succeeds" silently

    monkeypatch.setattr("hivereach._install_helpers.subprocess.run", _run)
    with patch(
        "hivereach._install_helpers.shutil.which",
        side_effect=[None, "/usr/bin/pipx", "/usr/bin/uv", "/usr/bin/bili"],
    ):
        install_pipx_tool(
            label="Bilibili (bili-cli)",
            binary="bili",
            package="bilibili-cli",
        )

    assert calls == [
        ["pipx", "install", "bilibili-cli"],
        ["uv", "tool", "install", "bilibili-cli"],
    ]
    assert "✅ bilibili-cli installed" in capsys.readouterr().out

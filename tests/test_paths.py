# -*- coding: utf-8 -*-
"""Behavior tests for cross-platform path and remediation helpers."""

import shutil
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_reach.utils import paths


def test_make_private_dir_skips_chmod_when_already_private(monkeypatch, tmp_path):
    target = tmp_path / "private"
    target.mkdir(mode=0o700)
    calls = []

    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setattr(paths.os, "open", lambda *_args: 42)
    monkeypatch.setattr(paths.os, "close", lambda _fd: None)
    monkeypatch.setattr(
        paths.os,
        "fstat",
        lambda _fd: SimpleNamespace(st_mode=stat.S_IFDIR | 0o700),
    )
    monkeypatch.setattr(
        paths.os, "fchmod", lambda *args: calls.append(args), raising=False
    )

    assert paths.make_private_dir(target) == target
    assert calls == []


def test_make_private_dir_warns_when_sandbox_denies_chmod(monkeypatch, tmp_path):
    target = tmp_path / "private"
    target.mkdir(mode=0o755)

    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setattr(paths.os, "open", lambda *_args: 42)
    monkeypatch.setattr(paths.os, "close", lambda _fd: None)
    monkeypatch.setattr(
        paths.os,
        "fstat",
        lambda _fd: SimpleNamespace(st_mode=stat.S_IFDIR | 0o755),
    )

    def deny_chmod(*_args):
        raise PermissionError("chmod denied by sandbox")

    monkeypatch.setattr(paths.os, "fchmod", deny_chmod, raising=False)

    with pytest.warns(RuntimeWarning, match="无法收紧"):
        assert paths.make_private_dir(target) == target


def test_make_private_dir_repairs_existing_mode(monkeypatch, tmp_path):
    target = tmp_path / "private"
    target.mkdir(mode=0o755)
    calls = []

    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setattr(paths.os, "open", lambda *_args: 42)
    monkeypatch.setattr(paths.os, "close", lambda _fd: None)
    monkeypatch.setattr(
        paths.os,
        "fstat",
        lambda _fd: SimpleNamespace(st_mode=stat.S_IFDIR | 0o755),
    )
    monkeypatch.setattr(
        paths.os, "fchmod", lambda *args: calls.append(args), raising=False
    )

    assert paths.make_private_dir(target) == target
    assert calls == [(42, 0o700)]


def test_posix_ytdlp_fix_is_single_line_executable_and_idempotent(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME")

    command = paths.render_ytdlp_fix_command()

    assert "\n" not in command
    shell = shutil.which("sh")
    if not shell:
        pytest.skip("POSIX sh is unavailable on this platform")
    subprocess.run([shell, "-c", command], check=True)
    subprocess.run([shell, "-c", command], check=True)

    config = tmp_path / ".config" / "yt-dlp" / "config"
    assert config.read_text(encoding="utf-8") == "--js-runtimes node\n"


def test_ytdlp_config_dir_matches_upstream_first_user_location(
    monkeypatch, tmp_path
):
    from yt_dlp.options import get_user_config_dirs

    config_home = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    expected = Path(next(get_user_config_dirs("yt-dlp")))

    assert paths.get_ytdlp_config_dir() == expected

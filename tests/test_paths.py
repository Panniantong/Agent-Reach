# -*- coding: utf-8 -*-
"""Behavior tests for cross-platform path and remediation helpers."""

import subprocess
from pathlib import Path

import pytest

from agent_reach.utils import paths


def test_posix_ytdlp_fix_is_single_line_executable_and_idempotent(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME")

    command = paths.render_ytdlp_fix_command()

    assert "\n" not in command
    subprocess.run(["/bin/sh", "-c", command], check=True)
    subprocess.run(["/bin/sh", "-c", command], check=True)

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


def test_user_home_resolves_symlinked_home(monkeypatch, tmp_path):
    """A symlinked ``$HOME`` (relocated /home, NFS, bind-mount) resolves to
    its real target so paths built beneath it don't trip the symlink guard."""
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    linked_home = tmp_path / "linked-home"
    try:
        linked_home.symlink_to(real_home, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform")

    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: linked_home))

    resolved = paths.user_home()

    assert resolved == real_home
    # Whatever agent-reach builds beneath it is now symlink-free end to end.
    paths.ensure_no_symlink_path(resolved / ".agent-reach" / "config.yaml")


def test_user_home_still_rejects_symlink_inside_home(monkeypatch, tmp_path):
    """Resolving the home *prefix* must not weaken the guard on components the
    tool creates below it: a link planted inside home is still refused."""
    real_home = tmp_path / "myhome"
    real_home.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    linked_child = real_home / ".agent-reach"
    try:
        linked_child.symlink_to(victim, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform")

    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: real_home))

    with pytest.raises(paths.PrivatePathError, match="符号链接"):
        paths.ensure_no_symlink_path(
            paths.user_home() / ".agent-reach" / "config.yaml"
        )

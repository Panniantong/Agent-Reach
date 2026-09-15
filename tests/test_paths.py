# -*- coding: utf-8 -*-
"""Behavior tests for cross-platform path and remediation helpers."""

import shutil
import subprocess
from pathlib import Path

import pytest

from agent_reach.utils import paths


def test_posix_ytdlp_fix_is_single_line_executable_and_idempotent(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("HOME", str(tmp_path))
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


def test_ytdlp_config_dir_matches_upstream_without_xdg_config_home(
    monkeypatch, tmp_path
):
    """The ``~/.config`` fallback must also agree with real yt-dlp.

    The XDG case above never reaches yt-dlp's ``compat_expanduser``, which is
    where the two implementations can diverge.
    """
    from yt_dlp.options import get_user_config_dirs

    monkeypatch.delenv("XDG_CONFIG_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))

    expected = Path(next(get_user_config_dirs("yt-dlp")))

    assert paths.get_ytdlp_config_dir() == expected


def test_ytdlp_config_dir_follows_home_when_it_differs_from_path_home(
    monkeypatch, tmp_path
):
    """Follow ``HOME`` even when ``Path.home()`` resolves somewhere else.

    That split is the normal state of affairs on Windows: ``expanduser`` there
    ignores ``HOME`` and returns ``USERPROFILE``, while yt-dlp's
    ``compat_expanduser`` deliberately honors ``HOME`` (yt-dlp#792). Following
    ``Path.home()`` writes ``--js-runtimes node`` to a file the real yt-dlp
    process never reads, and Doctor then reads back its own write and reports
    YouTube as healthy.
    """
    explicit_home = tmp_path / "explicit-home"
    user_profile = tmp_path / "user-profile"

    monkeypatch.delenv("XDG_CONFIG_HOME")
    monkeypatch.setenv("HOME", str(explicit_home))
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: user_profile))

    assert paths.get_ytdlp_config_dir() == explicit_home / ".config" / "yt-dlp"

"""Qoder skill discovery and lifecycle integration."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_reach.cli import _cmd_uninstall, _install_skill, _uninstall_skill


def test_install_skill_discovers_qoder_global_directory(tmp_path: Path):
    skill_parent = tmp_path / ".qoder" / "skills"
    skill_parent.mkdir(parents=True)

    with (
        patch(
            "agent_reach.cli.os.path.expanduser",
            side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
        ),
        patch.dict(os.environ, {}, clear=True),
    ):
        _install_skill()

    installed = skill_parent / "agent-reach" / "SKILL.md"
    assert installed.is_file()
    assert "Agent Reach" in installed.read_text(encoding="utf-8")


def test_install_skill_honors_qoder_config_dir(tmp_path: Path):
    qoder_home = tmp_path / "custom-qoder"
    (qoder_home / "skills").mkdir(parents=True)

    with patch.dict(os.environ, {"QODER_CONFIG_DIR": os.fspath(qoder_home)}, clear=True):
        _install_skill()

    assert (qoder_home / "skills" / "agent-reach" / "SKILL.md").is_file()


def test_uninstall_skill_removes_qoder_global_directory(tmp_path: Path):
    installed = tmp_path / ".qoder" / "skills" / "agent-reach"
    installed.mkdir(parents=True)
    (installed / "SKILL.md").write_text("test", encoding="utf-8")

    with (
        patch(
            "agent_reach.cli.os.path.expanduser",
            side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
        ),
        patch.dict(os.environ, {}, clear=True),
    ):
        _uninstall_skill()

    assert not installed.exists()


def test_full_uninstall_includes_custom_qoder_directory(tmp_path: Path, capsys):
    qoder_home = tmp_path / "custom-qoder"
    installed = qoder_home / "skills" / "agent-reach"
    installed.mkdir(parents=True)

    with (
        patch.dict(os.environ, {"QODER_CONFIG_DIR": os.fspath(qoder_home)}, clear=True),
        patch("agent_reach.utils.paths.home_dir", return_value=tmp_path),
        patch("shutil.which", return_value=None),
    ):
        _cmd_uninstall(SimpleNamespace(dry_run=True, keep_config=True))

    assert f"Would remove Qoder skill: {installed}" in capsys.readouterr().out
    assert installed.is_dir()

"""OpenCode discovery and metadata compatibility for the packaged skill."""

from __future__ import annotations

import importlib.resources
import os
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from agent_reach.cli import _cmd_uninstall, _install_skill, _uninstall_skill


def _frontmatter(resource_name: str) -> dict[str, object]:
    text = (
        importlib.resources.files("agent_reach")
        .joinpath("skill", resource_name)
        .read_text(encoding="utf-8")
    )
    match = re.match(r"\A---\n(.*?)\n---\n", text, flags=re.DOTALL)
    assert match is not None, f"{resource_name} must start with YAML frontmatter"
    return yaml.safe_load(match.group(1))


def test_skill_frontmatter_uses_opencode_supported_fields():
    """Both locale variants must follow OpenCode's documented schema."""
    allowed_fields = {
        "name",
        "description",
        "license",
        "compatibility",
        "metadata",
    }

    for resource_name in ("SKILL.md", "SKILL_en.md"):
        frontmatter = _frontmatter(resource_name)
        assert set(frontmatter) <= allowed_fields, resource_name
        assert frontmatter["name"] == "agent-reach", resource_name

        description = frontmatter["description"]
        assert isinstance(description, str), resource_name
        assert 1 <= len(description) <= 1024, resource_name

        metadata = frontmatter.get("metadata", {})
        assert isinstance(metadata, dict), resource_name
        assert all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in metadata.items()
        ), resource_name


def test_install_skill_uses_opencode_directory_only_when_requested(tmp_path: Path):
    """OpenCode is opt-in: an existing root is no longer enough to be written."""
    skill_parent = tmp_path / ".config" / "opencode" / "skills"
    skill_parent.mkdir(parents=True)
    installed = skill_parent / "agent-reach" / "SKILL.md"

    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
    ), patch.dict(os.environ, {}, clear=True):
        _install_skill()

        assert not installed.exists()

        _install_skill(all_clients=True)

    assert installed.is_file()
    assert "Agent Reach" in installed.read_text(encoding="utf-8")


def test_uninstall_skill_removes_opencode_directory_only_when_requested(
    tmp_path: Path,
):
    """Uninstall mirrors install: OpenCode is left alone unless asked for."""
    installed = tmp_path / ".config" / "opencode" / "skills" / "agent-reach"
    installed.mkdir(parents=True)
    (installed / "SKILL.md").write_text("test", encoding="utf-8")

    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
    ), patch.dict(os.environ, {}, clear=True):
        _uninstall_skill()

        assert installed.exists()

        _uninstall_skill(all_clients=True)

    assert not installed.exists()


def test_full_uninstall_includes_opencode_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    installed = tmp_path / ".config" / "opencode" / "skills" / "agent-reach"
    installed.mkdir(parents=True)

    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: os.fspath(
            tmp_path / value.removeprefix("~/")
        )
        if value.startswith("~/")
        else value,
    ), patch("agent_reach.utils.paths.home_dir", return_value=tmp_path), patch(
        "shutil.which", return_value=None
    ):
        _cmd_uninstall(SimpleNamespace(dry_run=True, keep_config=True))

    output = capsys.readouterr().out
    assert f"Would remove OpenCode skill: {installed}" in output
    assert installed.is_dir()

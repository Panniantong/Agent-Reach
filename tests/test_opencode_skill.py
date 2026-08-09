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


def test_install_docs_explain_profile_safe_hermes_registration():
    install_doc = (
        Path(__file__).resolve().parents[1] / "docs" / "install.md"
    ).read_text(encoding="utf-8")

    assert "Hermes Agent" in install_doc
    assert "HERMES_HOME" in install_doc
    assert "absolute" in install_doc
    assert "agent-reach skill --install" in install_doc


def test_install_skill_discovers_opencode_global_directory(tmp_path: Path):
    skill_parent = tmp_path / ".config" / "opencode" / "skills"
    skill_parent.mkdir(parents=True)

    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
    ), patch.dict(os.environ, {}, clear=True):
        _install_skill()

    installed = skill_parent / "agent-reach" / "SKILL.md"
    assert installed.is_file()
    assert "Agent Reach" in installed.read_text(encoding="utf-8")


def test_install_skill_discovers_active_hermes_profile(tmp_path: Path):
    hermes_home = tmp_path / "profiles" / "research"
    hermes_home.mkdir(parents=True)
    skill_parent = hermes_home / "skills"

    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
    ), patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ):
        _install_skill()

    installed = skill_parent / "agent-reach" / "SKILL.md"
    assert installed.is_file()
    assert "Agent Reach" in installed.read_text(encoding="utf-8")


def test_install_skill_skips_unusable_hermes_skills_child(tmp_path: Path):
    hermes_home = tmp_path / "profiles" / "research"
    hermes_home.mkdir(parents=True)
    (hermes_home / "skills").write_text("not a directory", encoding="utf-8")
    fallback_parent = tmp_path / ".agents" / "skills"
    fallback_parent.mkdir(parents=True)

    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
    ), patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ):
        _install_skill()

    assert (fallback_parent / "agent-reach" / "SKILL.md").is_file()


def test_uninstall_skill_removes_opencode_global_directory(tmp_path: Path):
    installed = tmp_path / ".config" / "opencode" / "skills" / "agent-reach"
    installed.mkdir(parents=True)
    (installed / "SKILL.md").write_text("test", encoding="utf-8")

    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
    ), patch.dict(os.environ, {}, clear=True):
        _uninstall_skill()

    assert not installed.exists()


def test_uninstall_skill_removes_active_hermes_profile(tmp_path: Path):
    hermes_home = tmp_path / "profiles" / "research"
    installed = hermes_home / "skills" / "agent-reach"
    installed.mkdir(parents=True)
    (installed / "SKILL.md").write_text("test", encoding="utf-8")

    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
    ), patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ):
        _uninstall_skill()

    assert not installed.exists()


@pytest.mark.parametrize("hermes_home", ["", "   ", "relative-profile"])
def test_uninstall_skill_ignores_unsafe_hermes_home_values(
    tmp_path: Path, hermes_home: str, monkeypatch: pytest.MonkeyPatch
):
    project_skill = tmp_path / "skills" / "agent-reach"
    project_skill.mkdir(parents=True)
    (project_skill / "SKILL.md").write_text("keep", encoding="utf-8")

    default_skill = tmp_path / ".hermes" / "skills" / "agent-reach"
    default_skill.mkdir(parents=True)
    (default_skill / "SKILL.md").write_text("remove", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
    ), patch.dict(
        os.environ,
        {"HERMES_HOME": hermes_home},
        clear=True,
    ):
        _uninstall_skill()

    assert project_skill.is_dir()
    assert not default_skill.exists()


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


def test_full_uninstall_includes_active_hermes_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    hermes_home = tmp_path / "profiles" / "research"
    installed = hermes_home / "skills" / "agent-reach"
    installed.mkdir(parents=True)

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ), patch("agent_reach.utils.paths.home_dir", return_value=tmp_path), patch(
        "shutil.which", return_value=None
    ):
        _cmd_uninstall(SimpleNamespace(dry_run=True, keep_config=True))

    output = capsys.readouterr().out
    assert f"Would remove Hermes skill: {installed}" in output
    assert installed.is_dir()


@pytest.mark.parametrize("hermes_home", ["", "   ", "relative-profile"])
def test_full_uninstall_ignores_unsafe_hermes_home_values(
    tmp_path: Path, hermes_home: str, monkeypatch: pytest.MonkeyPatch
):
    project_skill = tmp_path / "skills" / "agent-reach"
    project_skill.mkdir(parents=True)
    default_skill = tmp_path / ".hermes" / "skills" / "agent-reach"
    default_skill.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
    ), patch.dict(
        os.environ,
        {"HERMES_HOME": hermes_home},
        clear=True,
    ), patch("agent_reach.utils.paths.home_dir", return_value=tmp_path), patch(
        "shutil.which", return_value=None
    ):
        _cmd_uninstall(SimpleNamespace(dry_run=False, keep_config=True))

    assert project_skill.is_dir()
    assert not default_skill.exists()

"""OpenCode discovery and metadata compatibility for the packaged skill."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from agent_reach.cli import (
    _cmd_uninstall,
    _install_skill,
    _resolve_hermes_home,
    _uninstall_skill,
)


def _mark_agent_reach_owned(skill_path: Path) -> None:
    files = {
        path.relative_to(skill_path).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in skill_path.rglob("*")
        if path.is_file() and path.name != ".agent-reach-owner.json"
    }
    (skill_path / ".agent-reach-owner.json").write_text(
        json.dumps({"schema": 1, "owner": "agent-reach", "files": files}),
        encoding="utf-8",
    )


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
    assert "agent-reach skill --install --target hermes" in install_doc
    assert "creates `~/.hermes/skills/`" in install_doc


def test_default_hermes_install_creates_missing_skill_root(tmp_path: Path):
    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
    ), patch.dict(os.environ, {}, clear=True):
        assert _install_skill(target_client="hermes", force=False)

    assert (tmp_path / ".hermes" / "skills" / "agent-reach" / "SKILL.md").is_file()


def test_force_install_is_transactional_when_atomic_publish_fails(tmp_path: Path):
    hermes_home = tmp_path / "profile"
    target = hermes_home / "skills" / "agent-reach"
    target.mkdir(parents=True)
    original = target / "SKILL.md"
    original.write_text("original custom skill\n", encoding="utf-8")
    real_replace = os.replace
    calls = 0

    def fail_publish(source: str, destination: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected publish failure")
        real_replace(source, destination)

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ), patch("agent_reach.cli.os.replace", side_effect=fail_publish):
        assert not _install_skill(target_client="hermes", force=True)

    assert original.read_text(encoding="utf-8") == "original custom skill\n"
    assert sorted(path.name for path in target.parent.iterdir()) == ["agent-reach"]


def test_install_reads_each_packaged_resource_only_once(tmp_path: Path):
    hermes_home = tmp_path / "profile"
    hermes_home.mkdir()
    package_root = Path(__file__).resolve().parents[1] / "agent_reach"
    reads: dict[str, int] = {}
    real_read_text = Path.read_text

    def counted_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if package_root / "skill" in path.parents:
            relative = os.fspath(path.relative_to(package_root / "skill"))
            reads[relative] = reads.get(relative, 0) + 1
        return real_read_text(path, *args, **kwargs)

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ), patch("pathlib.Path.read_text", autospec=True, side_effect=counted_read_text):
        assert _install_skill(target_client="hermes", force=False)

    assert reads
    assert all(count == 1 for count in reads.values()), reads


def test_implicit_system_install_never_forces_skill_replacement():
    args = SimpleNamespace(
        safe=False,
        system=True,
        dry_run=False,
        channels="",
        proxy="",
        env="local",
    )
    with patch("agent_reach.cli._install_system_deps", return_value=True), patch(
        "agent_reach.cli._install_mcporter", return_value=True
    ), patch("agent_reach.doctor.check_all", return_value={}), patch(
        "agent_reach.doctor.format_report", return_value=""
    ), patch("agent_reach.cli._install_skill", return_value=True) as install_skill:
        from agent_reach.cli import _cmd_install

        _cmd_install(args)

    install_skill.assert_called_once_with(force=False)


def test_resolve_hermes_home_canonicalizes_symlinked_profile(tmp_path: Path):
    profile = tmp_path / "profiles" / "research"
    profile.mkdir(parents=True)
    profile_link = tmp_path / "profile-link"
    profile_link.symlink_to(profile, target_is_directory=True)

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(profile_link)},
        clear=True,
    ):
        resolved, explicit = _resolve_hermes_home()

    assert explicit is True
    assert resolved == os.path.realpath(profile)


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


def test_targeted_hermes_install_is_guarded_and_profile_isolated(tmp_path: Path):
    hermes_home = tmp_path / "profiles" / "research"
    hermes_home.mkdir(parents=True)
    other_skill_root = tmp_path / ".agents" / "skills"
    other_skill_root.mkdir(parents=True)

    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
    ), patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ):
        assert _install_skill(target_client="hermes", force=False)

    installed = hermes_home / "skills" / "agent-reach" / "SKILL.md"
    content = installed.read_text(encoding="utf-8")
    assert "read-only research on unsupported social sites" in content
    assert "MUST USE" not in content
    assert not (other_skill_root / "agent-reach").exists()


def test_targeted_hermes_install_preserves_existing_skill_without_force(tmp_path: Path):
    hermes_home = tmp_path / "profiles" / "research"
    installed = hermes_home / "skills" / "agent-reach"
    installed.mkdir(parents=True)
    custom = installed / "SKILL.md"
    custom.write_text("custom guard\n", encoding="utf-8")

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ):
        assert _install_skill(target_client="hermes", force=False)

    assert custom.read_text(encoding="utf-8") == "custom guard\n"


def test_targeted_hermes_install_preserves_existing_dangling_skill_symlink(
    tmp_path: Path,
):
    hermes_home = tmp_path / "profiles" / "research"
    installed = hermes_home / "skills" / "agent-reach"
    installed.parent.mkdir(parents=True)
    missing_target = tmp_path / "missing-skill"
    installed.symlink_to(missing_target, target_is_directory=True)

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ):
        assert _install_skill(target_client="hermes", force=False)

    assert installed.is_symlink()
    assert os.readlink(installed) == os.fspath(missing_target)


def test_install_skill_skips_symlinked_hermes_skills_child(tmp_path: Path):
    hermes_home = tmp_path / "profiles" / "research"
    hermes_home.mkdir(parents=True)
    external_skills = tmp_path / "external-skills"
    external_skills.mkdir()
    (hermes_home / "skills").symlink_to(external_skills, target_is_directory=True)
    fallback_root = tmp_path / ".agents" / "skills"
    fallback_root.mkdir(parents=True)

    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
    ), patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ):
        assert _install_skill(force=False)

    assert not (external_skills / "agent-reach").exists()
    assert (fallback_root / "agent-reach" / "SKILL.md").is_file()


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


def test_targeted_hermes_install_refuses_default_symlinked_skills_root(tmp_path: Path):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    external = tmp_path / "external-skills"
    external.mkdir()
    (hermes_home / "skills").symlink_to(external, target_is_directory=True)

    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
    ), patch.dict(os.environ, {}, clear=True):
        assert not _install_skill(target_client="hermes", force=False)

    assert not (external / "agent-reach").exists()


def test_targeted_hermes_install_fails_closed_without_guarded_resource(tmp_path: Path):
    hermes_home = tmp_path / "profile"
    hermes_home.mkdir()
    package_root = tmp_path / "package"
    skill_root = package_root / "skill"
    (skill_root / "references").mkdir(parents=True)
    (skill_root / "SKILL.md").write_text("unrestricted\n", encoding="utf-8")

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ), patch("importlib.resources.files", return_value=package_root):
        assert not _install_skill(target_client="hermes", force=True)

    assert not (hermes_home / "skills").exists()


def test_targeted_hermes_force_replaces_regular_file_target(tmp_path: Path):
    hermes_home = tmp_path / "profile"
    target = hermes_home / "skills" / "agent-reach"
    target.parent.mkdir(parents=True)
    target.write_text("blocking file\n", encoding="utf-8")

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ):
        assert _install_skill(target_client="hermes", force=True)

    assert target.is_dir()
    assert (target / "SKILL.md").is_file()


def test_uninstall_refuses_symlinked_hermes_skills_root(tmp_path: Path):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    external = tmp_path / "external-skills"
    installed = external / "agent-reach"
    installed.mkdir(parents=True)
    (hermes_home / "skills").symlink_to(external, target_is_directory=True)

    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
    ), patch.dict(os.environ, {}, clear=True):
        assert not _uninstall_skill(target_client="hermes")

    assert installed.is_dir()


def test_uninstall_refuses_symlinked_legacy_hermes_parent(tmp_path: Path):
    hermes_home = tmp_path / "profile"
    skills = hermes_home / "skills"
    skills.mkdir(parents=True)
    external = tmp_path / "external-social"
    installed = external / "agent-reach"
    installed.mkdir(parents=True)
    (skills / "social-media").symlink_to(external, target_is_directory=True)

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ):
        assert not _uninstall_skill(target_client="hermes")

    assert installed.is_dir()


def test_full_uninstall_refuses_symlinked_hermes_skills_root(tmp_path: Path):
    hermes_home = tmp_path / "profile"
    hermes_home.mkdir()
    external = tmp_path / "external-skills"
    installed = external / "agent-reach"
    installed.mkdir(parents=True)
    (hermes_home / "skills").symlink_to(external, target_is_directory=True)

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ), patch("agent_reach.utils.paths.home_dir", return_value=tmp_path), patch(
        "shutil.which", return_value=None
    ), pytest.raises(SystemExit) as raised:
        _cmd_uninstall(SimpleNamespace(dry_run=False, keep_config=True))

    assert raised.value.code == 1
    assert installed.is_dir()


def test_full_uninstall_refuses_symlinked_legacy_hermes_parent(tmp_path: Path):
    hermes_home = tmp_path / "profile"
    skills = hermes_home / "skills"
    skills.mkdir(parents=True)
    external = tmp_path / "external-social"
    installed = external / "agent-reach"
    installed.mkdir(parents=True)
    (skills / "social-media").symlink_to(external, target_is_directory=True)

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ), patch("agent_reach.utils.paths.home_dir", return_value=tmp_path), patch(
        "shutil.which", return_value=None
    ), pytest.raises(SystemExit) as raised:
        _cmd_uninstall(SimpleNamespace(dry_run=False, keep_config=True))

    assert raised.value.code == 1
    assert installed.is_dir()


def test_uninstall_preserves_unmarked_legacy_skill_and_reports_failure(tmp_path: Path):
    hermes_home = tmp_path / "profile"
    legacy = hermes_home / "skills" / "social-media" / "agent-reach"
    legacy.mkdir(parents=True)
    custom = legacy / "SKILL.md"
    custom.write_text("unrelated custom skill\n", encoding="utf-8")

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ):
        assert not _uninstall_skill(target_client="hermes")

    assert custom.read_text(encoding="utf-8") == "unrelated custom skill\n"


def test_uninstall_owned_skill_preserves_unrelated_custom_files(tmp_path: Path):
    hermes_home = tmp_path / "profile"
    hermes_home.mkdir()
    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ):
        assert _install_skill(target_client="hermes", force=False)

    canonical = hermes_home / "skills" / "agent-reach"
    custom = canonical / "custom-notes.md"
    custom.write_text("keep me\n", encoding="utf-8")

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ):
        assert _uninstall_skill(target_client="hermes")

    assert custom.read_text(encoding="utf-8") == "keep me\n"
    assert not (canonical / "SKILL.md").exists()


def test_uninstall_refuses_owned_skill_when_managed_file_was_modified(tmp_path: Path):
    hermes_home = tmp_path / "profile"
    hermes_home.mkdir()
    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ):
        assert _install_skill(target_client="hermes", force=False)

    installed = hermes_home / "skills" / "agent-reach"
    skill_md = installed / "SKILL.md"
    skill_md.write_text("locally customized\n", encoding="utf-8")

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ):
        assert not _uninstall_skill(target_client="hermes")

    assert skill_md.read_text(encoding="utf-8") == "locally customized\n"


def test_full_uninstall_returns_nonzero_when_skill_cleanup_is_refused(tmp_path: Path):
    hermes_home = tmp_path / "profile"
    legacy = hermes_home / "skills" / "social-media" / "agent-reach"
    legacy.mkdir(parents=True)
    (legacy / "SKILL.md").write_text("custom\n", encoding="utf-8")

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ), patch("agent_reach.utils.paths.home_dir", return_value=tmp_path), patch(
        "shutil.which", return_value=None
    ), pytest.raises(SystemExit) as raised:
        _cmd_uninstall(SimpleNamespace(dry_run=False, keep_config=True))

    assert raised.value.code == 1
    assert legacy.is_dir()


def test_uninstall_skill_removes_opencode_global_directory(tmp_path: Path):
    installed = tmp_path / ".config" / "opencode" / "skills" / "agent-reach"
    installed.mkdir(parents=True)
    (installed / "SKILL.md").write_text("test", encoding="utf-8")
    _mark_agent_reach_owned(installed)

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
    _mark_agent_reach_owned(installed)

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


def test_targeted_hermes_uninstall_removes_canonical_and_legacy_pilot_only(
    tmp_path: Path,
):
    hermes_home = tmp_path / "profiles" / "research"
    canonical = hermes_home / "skills" / "agent-reach"
    legacy = hermes_home / "skills" / "social-media" / "agent-reach"
    other = tmp_path / ".agents" / "skills" / "agent-reach"
    for target in (canonical, legacy, other):
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("test", encoding="utf-8")
    _mark_agent_reach_owned(canonical)
    _mark_agent_reach_owned(legacy)

    with patch(
        "agent_reach.cli.os.path.expanduser",
        side_effect=lambda value: value.replace("~", os.fspath(tmp_path)),
    ), patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ):
        _uninstall_skill(target_client="hermes")

    assert not canonical.exists()
    assert not legacy.exists()
    assert other.is_dir()


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
    _mark_agent_reach_owned(default_skill)

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
    _mark_agent_reach_owned(installed)

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
    _mark_agent_reach_owned(installed)

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


def test_full_uninstall_includes_legacy_categorized_hermes_pilot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    hermes_home = tmp_path / "profiles" / "research"
    installed = hermes_home / "skills" / "social-media" / "agent-reach"
    installed.mkdir(parents=True)
    _mark_agent_reach_owned(installed)

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ), patch("agent_reach.utils.paths.home_dir", return_value=tmp_path), patch(
        "shutil.which", return_value=None
    ):
        _cmd_uninstall(SimpleNamespace(dry_run=True, keep_config=True))

    output = capsys.readouterr().out
    assert f"Would remove Hermes legacy pilot skill: {installed}" in output
    assert installed.is_dir()


def test_full_uninstall_refuses_dangling_hermes_skill_symlink(tmp_path: Path):
    hermes_home = tmp_path / "profiles" / "research"
    installed = hermes_home / "skills" / "agent-reach"
    installed.parent.mkdir(parents=True)
    installed.symlink_to(tmp_path / "missing-target", target_is_directory=True)

    with patch.dict(
        os.environ,
        {"HERMES_HOME": os.fspath(hermes_home)},
        clear=True,
    ), patch("agent_reach.utils.paths.home_dir", return_value=tmp_path), patch(
        "shutil.which", return_value=None
    ), pytest.raises(SystemExit) as raised:
        _cmd_uninstall(SimpleNamespace(dry_run=False, keep_config=True))

    assert raised.value.code == 1
    assert os.path.lexists(installed)


def test_full_uninstall_recommends_uv_tool_removal_when_uv_is_available(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    with patch("agent_reach.utils.paths.home_dir", return_value=tmp_path), patch(
        "shutil.which",
        side_effect=lambda command: "/usr/bin/uv" if command == "uv" else None,
    ):
        _cmd_uninstall(SimpleNamespace(dry_run=True, keep_config=True))

    assert "uv tool uninstall agent-reach" in capsys.readouterr().out


@pytest.mark.parametrize("hermes_home", ["", "   ", "relative-profile"])
def test_full_uninstall_ignores_unsafe_hermes_home_values(
    tmp_path: Path, hermes_home: str, monkeypatch: pytest.MonkeyPatch
):
    project_skill = tmp_path / "skills" / "agent-reach"
    project_skill.mkdir(parents=True)
    default_skill = tmp_path / ".hermes" / "skills" / "agent-reach"
    default_skill.mkdir(parents=True)
    _mark_agent_reach_owned(default_skill)

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

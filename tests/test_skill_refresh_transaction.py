"""A failed refresh must preserve an existing usable skill installation."""

import importlib.resources

from agent_reach import cli


def _existing_skill(home):
    target = home / ".agents" / "skills" / "agent-reach"
    (target / "references").mkdir(parents=True)
    (target / "SKILL.md").write_text("previous usable skill", encoding="utf-8")
    (target / "references" / "web.md").write_text("previous reference", encoding="utf-8")
    return target


def _package_fixture(tmp_path, monkeypatch, reference):
    package = tmp_path / "package"
    skill = package / "skill"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text("replacement skill", encoding="utf-8")
    (skill / "SKILL_en.md").write_text("replacement skill", encoding="utf-8")
    (skill / "references" / "web.md").write_bytes(reference)
    monkeypatch.setattr(importlib.resources, "files", lambda _name: package)


def test_unreadable_packaged_reference_preserves_prior_skill(
    isolated_home,
    tmp_path,
    monkeypatch,
):
    target = _existing_skill(isolated_home)
    _package_fixture(tmp_path, monkeypatch, b"\xff invalid UTF-8")
    assert not cli._install_skill()
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "previous usable skill"
    assert (target / "references" / "web.md").read_text(encoding="utf-8") == "previous reference"
    assert sorted(path.name for path in target.parent.iterdir()) == ["agent-reach"]


def test_completed_refresh_replaces_old_skill_and_references(
    isolated_home,
    tmp_path,
    monkeypatch,
):
    target = _existing_skill(isolated_home)
    _package_fixture(tmp_path, monkeypatch, b"replacement reference")
    assert cli._install_skill()
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "replacement skill"
    assert (target / "references" / "web.md").read_text(encoding="utf-8") == "replacement reference"
    assert sorted(path.name for path in target.parent.iterdir()) == ["agent-reach"]


def test_reference_write_failure_preserves_prior_skill(
    isolated_home,
    tmp_path,
    monkeypatch,
):
    import builtins

    target = _existing_skill(isolated_home)
    _package_fixture(tmp_path, monkeypatch, b"replacement reference")
    original = builtins.open

    def write(path, mode="r", *args, **kwargs):
        if mode == "w" and str(path).endswith("references/web.md"):
            raise OSError("disk full")
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", write)
    assert not cli._install_skill()
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "previous usable skill"
    assert (target / "references" / "web.md").read_text(encoding="utf-8") == "previous reference"
    assert sorted(path.name for path in target.parent.iterdir()) == ["agent-reach"]


def test_failed_commit_restores_prior_skill(isolated_home, tmp_path, monkeypatch):
    import os

    target = _existing_skill(isolated_home)
    _package_fixture(tmp_path, monkeypatch, b"replacement reference")
    original = os.replace

    def replace(source, destination):
        if ".agent-reach-stage-" in str(source):
            raise PermissionError("commit denied")
        return original(source, destination)

    monkeypatch.setattr(os, "replace", replace)
    assert not cli._install_skill()
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "previous usable skill"
    assert (target / "references" / "web.md").read_text(encoding="utf-8") == "previous reference"
    assert sorted(path.name for path in target.parent.iterdir()) == ["agent-reach"]


def test_completed_refresh_replaces_symlink_without_changing_external_target(
    isolated_home, tmp_path, monkeypatch
):
    external = tmp_path / "external-skill"
    (external / "references").mkdir(parents=True)
    (external / "SKILL.md").write_text("external skill", encoding="utf-8")
    (external / "references" / "web.md").write_text("external reference", encoding="utf-8")
    target = isolated_home / ".agents" / "skills" / "agent-reach"
    target.parent.mkdir(parents=True)
    target.symlink_to(external, target_is_directory=True)
    _package_fixture(tmp_path, monkeypatch, b"replacement reference")

    assert cli._install_skill()
    assert not target.is_symlink()
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "replacement skill"
    assert (target / "references" / "web.md").read_text(encoding="utf-8") == "replacement reference"
    assert (external / "SKILL.md").read_text(encoding="utf-8") == "external skill"
    assert (external / "references" / "web.md").read_text(encoding="utf-8") == "external reference"
    assert sorted(path.name for path in target.parent.iterdir()) == ["agent-reach"]


def test_failed_restore_reports_retained_backup_location(
    isolated_home, tmp_path, monkeypatch, capsys
):
    import os

    target = _existing_skill(isolated_home)
    _package_fixture(tmp_path, monkeypatch, b"replacement reference")
    original = os.replace

    def replace(source, destination):
        if ".agent-reach-stage-" in str(source):
            raise PermissionError("commit denied")
        if ".agent-reach-old-" in str(source):
            raise PermissionError("restore denied")
        return original(source, destination)

    monkeypatch.setattr(os, "replace", replace)
    assert not cli._install_skill()
    backups = list(target.parent.glob(".agent-reach-old-*"))
    assert len(backups) == 1
    backup = backups[0]
    assert (backup / "SKILL.md").read_text(encoding="utf-8") == "previous usable skill"
    assert (backup / "references" / "web.md").read_text(encoding="utf-8") == "previous reference"
    assert not target.exists()
    assert str(backup) in capsys.readouterr().out
    assert not list(target.parent.glob(".agent-reach-stage-*"))

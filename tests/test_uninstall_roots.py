"""Cleanup follows the same explicit skill roots that installation supports."""

from argparse import Namespace

import pytest

from agent_reach import cli


def test_uninstall_removes_custom_openclaw_registration(tmp_path, monkeypatch):
    custom_home = tmp_path / "custom openclaw"
    skill = custom_home / ".openclaw" / "skills" / "agent-reach"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("installed", encoding="utf-8")
    unrelated = custom_home / "keep.txt"
    unrelated.write_text("user data", encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_HOME", str(custom_home))
    monkeypatch.setattr("shutil.which", lambda _name: None)
    cli._cmd_uninstall(Namespace(dry_run=False, keep_config=True))
    assert not skill.exists()
    assert unrelated.read_text(encoding="utf-8") == "user data"


def test_dry_run_reports_and_preserves_custom_openclaw_registration(
    tmp_path,
    monkeypatch,
    capsys,
):
    custom_home = tmp_path / "custom openclaw"
    skill = custom_home / ".openclaw" / "skills" / "agent-reach"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("installed", encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_HOME", str(custom_home))
    monkeypatch.setattr("shutil.which", lambda _name: None)
    cli._cmd_uninstall(Namespace(dry_run=True, keep_config=True))
    assert str(skill) in capsys.readouterr().out
    assert (skill / "SKILL.md").read_text(encoding="utf-8") == "installed"


@pytest.mark.parametrize("command", ["skill", "uninstall"])
def test_cleanup_removes_dangling_skill_link(isolated_home, monkeypatch, command):
    skill = isolated_home / ".agents" / "skills" / "agent-reach"
    skill.parent.mkdir(parents=True)
    try:
        skill.symlink_to(isolated_home / "missing-target", target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation not available")
    monkeypatch.setattr("shutil.which", lambda _name: None)
    if command == "skill":
        cli._uninstall_skill()
    else:
        cli._cmd_uninstall(Namespace(dry_run=False, keep_config=True))
    assert not skill.is_symlink()

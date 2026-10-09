"""An attempted cleanup failure must remain visible to automation."""

from argparse import Namespace

import pytest

from agent_reach import cli


@pytest.mark.parametrize("component", ["config", "skill"])
def test_uninstall_exits_nonzero_when_requested_removal_fails(
    isolated_home,
    monkeypatch,
    component,
):
    import shutil

    config = isolated_home / ".agent-reach"
    skill = isolated_home / ".agents" / "skills" / "agent-reach"
    blocked = config if component == "config" else skill
    blocked.mkdir(parents=True)
    (blocked / "keep.txt").write_text("still present", encoding="utf-8")
    original = shutil.rmtree

    def remove(path, *args, **kwargs):
        if str(path) == str(blocked):
            raise PermissionError("removal denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", remove)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(SystemExit) as error:
        cli._cmd_uninstall(Namespace(dry_run=False, keep_config=False))
    assert error.value.code == 1
    assert (blocked / "keep.txt").read_text(encoding="utf-8") == "still present"


def test_skill_uninstall_reports_failed_removal(isolated_home, monkeypatch):
    import shutil

    skill = isolated_home / ".agents" / "skills" / "agent-reach"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("still present", encoding="utf-8")
    original = shutil.rmtree

    def remove(path, *args, **kwargs):
        if str(path) == str(skill):
            raise PermissionError("removal denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", remove)
    with pytest.raises(SystemExit) as error:
        cli._cmd_skill(Namespace(install=False, uninstall=True))
    assert error.value.code == 1
    assert (skill / "SKILL.md").read_text(encoding="utf-8") == "still present"

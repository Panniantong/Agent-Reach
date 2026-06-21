"""Tests for agent_reach.paths — runtime path resolution."""

from pathlib import Path

import pytest

from agent_reach.paths import (
    agent_reach_home,
    config_file,
    tools_dir,
    xhs_cookie_file,
    xiaoyuzhou_tools_dir,
)


def test_default_paths_derive_from_user_home(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENT_REACH_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    assert agent_reach_home() == tmp_path / ".agent-reach"
    assert config_file() == tmp_path / ".agent-reach" / "config.yaml"
    assert tools_dir() == tmp_path / ".agent-reach" / "tools"
    assert xiaoyuzhou_tools_dir() == tmp_path / ".agent-reach" / "tools" / "xiaoyuzhou"
    assert xhs_cookie_file() == tmp_path / ".agent-reach" / "xhs-cookies.json"


def test_custom_home_overrides_default(monkeypatch, tmp_path):
    custom = tmp_path / "central" / "agent-reach"
    monkeypatch.setenv("AGENT_REACH_HOME", str(custom))

    assert agent_reach_home() == custom
    assert config_file() == custom / "config.yaml"


def test_relative_custom_home_is_rejected(monkeypatch):
    monkeypatch.setenv("AGENT_REACH_HOME", "relative/agent-reach")

    with pytest.raises(ValueError, match="AGENT_REACH_HOME must be an absolute path"):
        agent_reach_home()


# ── Config precedence tests ─────────────────────────


def test_config_uses_custom_home(monkeypatch, tmp_path):
    from agent_reach.config import Config

    custom = tmp_path / "custom"
    monkeypatch.setenv("AGENT_REACH_HOME", str(custom))

    config = Config()

    assert config.config_path == custom / "config.yaml"


def test_explicit_config_path_beats_custom_home(monkeypatch, tmp_path):
    from agent_reach.config import Config

    monkeypatch.setenv("AGENT_REACH_HOME", str(tmp_path / "custom"))
    explicit = tmp_path / "explicit.yaml"

    config = Config(config_path=explicit)

    assert config.config_path == explicit


# ── Path report tests ────────────────────────────


def test_path_report_separates_ownership(monkeypatch, tmp_path):
    from agent_reach.paths import path_report

    monkeypatch.setenv("AGENT_REACH_HOME", str(tmp_path / "managed"))
    monkeypatch.setattr("agent_reach.paths.shutil.which", lambda name: f"/bin/{name}")

    report = path_report()

    assert [item["key"] for item in report["managed"]] == [
        "home", "config", "tools", "xhs_cookies",
    ]
    assert all(item["owner"] == "agent-reach" for item in report["managed"])
    assert all(item["owner"] == "agent-platform" for item in report["registration"])
    assert all(item["owner"] == "upstream" for item in report["external"])
    assert next(item for item in report["external"] if item["key"] == "gh")["path"] == "/bin/gh"


def test_path_report_external_not_found_is_null(monkeypatch, tmp_path):
    from agent_reach.paths import path_report

    monkeypatch.setenv("AGENT_REACH_HOME", str(tmp_path / "managed"))
    monkeypatch.setattr("agent_reach.paths.shutil.which", lambda name: None)

    report = path_report()
    assert next(item for item in report["external"] if item["key"] == "gh")["path"] is None


def test_skill_registration_dirs_includes_known_platforms(monkeypatch, tmp_path):
    from agent_reach.paths import skill_registration_dirs

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("OPENCLAW_HOME", raising=False)

    dirs = skill_registration_dirs()
    dir_names = [str(d) for d in dirs]

    assert str(tmp_path / ".agents" / "skills" / "agent-reach") not in dir_names
    assert str(tmp_path / ".openclaw" / "skills" / "agent-reach") not in dir_names

    # skill_registration_dirs returns parent directories (without /agent-reach)
    expected_parents = [
        tmp_path / ".agents" / "skills",
        tmp_path / ".openclaw" / "skills",
        tmp_path / ".claude" / "skills",
    ]
    for parent in expected_parents:
        assert parent in dirs


def test_skill_registration_dirs_respects_openclaw_home(monkeypatch, tmp_path):
    from agent_reach.paths import skill_registration_dirs

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    custom_openclaw = tmp_path / "custom-openclaw"
    monkeypatch.setenv("OPENCLAW_HOME", str(custom_openclaw))

    dirs = skill_registration_dirs()
    assert dirs[0] == custom_openclaw / ".openclaw" / "skills"

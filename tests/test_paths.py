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

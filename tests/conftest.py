# -*- coding: utf-8 -*-
"""Shared pytest fixtures.

Sandboxes $HOME for every test. Several commands write into the user's
home directory as a side effect — most notably `agent-reach doctor`, which
auto-installs SKILL.md into every agent directory it finds
(~/.claude/skills, ~/.agents/skills, ~/.openclaw/skills) and creates
~/.agent-reach/ via Config(). Without this fixture, simply running the
test suite mutates the developer's real home directory and can silently
install/overwrite skill files for their live AI agents.

`os.path.expanduser("~")` and `pathlib.Path.home()` resolve from HOME on
POSIX and USERPROFILE on Windows, so redirecting those env vars contains
every *runtime* home-directed write (e.g. the skill-dir installs) under a
throwaway tmp dir. Config.CONFIG_DIR / CONFIG_FILE are the exception: they
are class attributes bound to Path.home() at import time — before any
fixture runs — so they must be re-pointed explicitly.
"""

import pytest

from agent_reach.config import Config


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # Windows

    config_dir = home / ".agent-reach"
    monkeypatch.setattr(Config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(Config, "CONFIG_FILE", config_dir / "config.yaml")
    return home

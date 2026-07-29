# -*- coding: utf-8 -*-
"""Suite-wide containment for tests that exercise user-facing installers."""

import pytest

from agent_reach.config import Config


@pytest.fixture
def symlink_or_skip():
    """Create a symlink or skip when the host has no symlink privilege."""

    def create(link, target, *, target_is_directory=False):
        try:
            link.symlink_to(target, target_is_directory=target_is_directory)
        except (NotImplementedError, OSError) as exc:
            pytest.skip(f"symlink creation is unavailable: {exc}")
        return link

    return create


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Redirect every common home/config root before each test runs."""
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    monkeypatch.delenv("OPENCLAW_HOME", raising=False)

    config_dir = home / ".agent-reach"
    monkeypatch.setattr(Config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(Config, "CONFIG_FILE", config_dir / "config.yaml")
    return home


@pytest.fixture(autouse=True)
def isolated_xueqiu_cookie_jar(monkeypatch):
    """Prevent the module-level Xueqiu session from leaking between tests."""
    from agent_reach.channels import xueqiu

    xueqiu._cookie_jar.clear()
    monkeypatch.setattr(xueqiu, "_cookies_initialized", False)
    yield
    xueqiu._cookie_jar.clear()

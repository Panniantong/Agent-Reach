# -*- coding: utf-8 -*-
"""Tests for read-only Hermes MCP configuration inspection."""

from pathlib import Path

import pytest

from agent_reach.channels.hermes import (
    HermesConfigError,
    inspect_hermes_mcp_config,
)


def _write_config(root: Path, text: str) -> Path:
    root.mkdir(parents=True, mode=0o700)
    path = root / "config.yaml"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


def test_inspector_reads_enabled_mcp_names_from_hermes_home(monkeypatch, tmp_path):
    hermes_home = tmp_path / "hermes"
    _write_config(
        hermes_home,
        """
mcp_servers:
  linkedin:
    command: uvx
    enabled: true
  jobspy:
    command: uvx
  disabled-server:
    command: disabled
    enabled: false
""".lstrip(),
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    inspection = inspect_hermes_mcp_config()

    assert inspection.server_names == {"linkedin", "jobspy"}
    assert inspection.source == str(hermes_home / "config.yaml")


def test_inspector_returns_empty_when_hermes_config_is_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "missing"))

    inspection = inspect_hermes_mcp_config()

    assert inspection.server_names == frozenset()
    assert inspection.source is None


def test_inspector_rejects_symlinked_config(monkeypatch, tmp_path):
    real = _write_config(tmp_path / "real", "mcp_servers: {}\n")
    hermes_home = tmp_path / "linked"
    hermes_home.mkdir()
    try:
        (hermes_home / "config.yaml").symlink_to(real)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    with pytest.raises(HermesConfigError, match="符号链接|安全读取"):
        inspect_hermes_mcp_config()


def test_inspector_rejects_non_mapping_server_definitions(monkeypatch, tmp_path):
    hermes_home = tmp_path / "hermes"
    _write_config(hermes_home, "mcp_servers:\n  linkedin: uvx\n")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    with pytest.raises(HermesConfigError, match="server 定义"):
        inspect_hermes_mcp_config()

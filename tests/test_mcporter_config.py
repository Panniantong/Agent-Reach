"""Read-only mcporter configuration inspection tests."""

from __future__ import annotations

import json

import pytest

from agent_reach.channels.mcporter import (
    McporterConfigError,
    configured_server_names,
    inspect_mcporter_config,
)


def _write_config(path, servers, *, imports=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"mcpServers": servers, "imports": list(imports)}),
        encoding="utf-8",
    )


def test_home_and_project_layers_are_merged(
    monkeypatch, tmp_path, isolated_home
):
    monkeypatch.chdir(tmp_path)
    _write_config(
        isolated_home / ".mcporter" / "mcporter.json",
        {
            "home-only": {"baseUrl": "https://home.example.test"},
            "shared": {"baseUrl": "https://home-shared.example.test"},
        },
    )
    _write_config(
        tmp_path / "config" / "mcporter.json",
        {
            "project-only": {"command": "project-mcp"},
            "shared": {"baseUrl": "https://project-shared.example.test"},
        },
    )

    inspection = inspect_mcporter_config()

    assert inspection.server_names == {
        "home-only",
        "project-only",
        "shared",
    }
    assert inspection.source == "home+project"
    assert inspection.imports_unchecked is False


def test_explicit_config_is_the_only_layer(
    monkeypatch, tmp_path, isolated_home
):
    monkeypatch.chdir(tmp_path)
    _write_config(
        isolated_home / ".mcporter" / "mcporter.json",
        {"home-only": {"command": "home"}},
    )
    _write_config(
        tmp_path / "config" / "mcporter.json",
        {"project-only": {"command": "project"}},
    )
    _write_config(
        tmp_path / "explicit.json",
        {"explicit-only": {"command": "explicit"}},
    )
    monkeypatch.setenv("MCPORTER_CONFIG", "explicit.json")

    inspection = inspect_mcporter_config()

    assert inspection.server_names == {"explicit-only"}
    assert inspection.source == "explicit"


def test_missing_explicit_config_fails_closed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MCPORTER_CONFIG", "missing.json")

    with pytest.raises(McporterConfigError, match="不存在"):
        inspect_mcporter_config()


def test_symlink_config_is_rejected(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "real.json"
    _write_config(target, {"exa": {"baseUrl": "https://example.test"}})
    config_path = tmp_path / "config" / "mcporter.json"
    config_path.parent.mkdir()
    try:
        config_path.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")

    with pytest.raises(McporterConfigError, match="符号链接"):
        inspect_mcporter_config()


def test_ancestor_symlink_config_is_rejected(monkeypatch, tmp_path):
    real_root = tmp_path / "real-root"
    _write_config(
        real_root / "config" / "mcporter.json",
        {"exa": {"baseUrl": "https://example.test"}},
    )
    linked_root = tmp_path / "linked-root"
    try:
        linked_root.symlink_to(real_root, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")
    monkeypatch.setenv(
        "MCPORTER_CONFIG",
        str(linked_root / "config" / "mcporter.json"),
    )

    with pytest.raises(McporterConfigError, match="安全读取"):
        inspect_mcporter_config()


def test_invalid_json_fails_closed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config" / "mcporter.json"
    config_path.parent.mkdir()
    config_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(McporterConfigError, match="UTF-8 JSON"):
        inspect_mcporter_config()


def test_omitted_imports_are_reported_but_not_expanded(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config" / "mcporter.json"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps({"mcpServers": {"exa": {"command": "exa"}}}),
        encoding="utf-8",
    )

    inspection = inspect_mcporter_config()

    assert inspection.server_names == {"exa"}
    assert inspection.imports_unchecked is True


def test_machine_output_parser_remains_available_for_install_flows():
    output = json.dumps(
        {
            "servers": [
                {"name": "Exa", "baseUrl": "https://example.test"},
                {"name": "linkedin-scraper"},
            ]
        }
    )

    assert configured_server_names(output) == {"exa", "linkedin-scraper"}

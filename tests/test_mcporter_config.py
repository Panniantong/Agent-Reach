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


def test_home_scope_ignores_a_project_layer_shadowing_the_name(
    monkeypatch, tmp_path, isolated_home
):
    """A bundled project entry is not an installed home entry."""
    monkeypatch.chdir(tmp_path)
    _write_config(
        isolated_home / ".mcporter" / "mcporter.json",
        {"home-only": {"command": "home"}},
    )
    _write_config(
        tmp_path / "config" / "mcporter.json",
        {"exa": {"baseUrl": "https://mcp.exa.ai/mcp"}},
    )

    assert inspect_mcporter_config().server_names == {"home-only", "exa"}
    home_only = inspect_mcporter_config(scope="home")

    assert home_only.server_names == {"home-only"}
    assert home_only.source == "home"


def test_home_scope_reads_nothing_when_home_config_is_absent(
    monkeypatch, tmp_path, isolated_home
):
    monkeypatch.chdir(tmp_path)
    _write_config(
        tmp_path / "config" / "mcporter.json",
        {"exa": {"baseUrl": "https://mcp.exa.ai/mcp"}},
    )

    assert inspect_mcporter_config(scope="home").server_names == frozenset()
    assert inspect_mcporter_config(scope="home").source is None


def test_home_scope_does_not_parse_the_project_layer(
    monkeypatch, tmp_path, isolated_home
):
    """An unrelated malformed project config must not break a home-scoped read."""
    monkeypatch.chdir(tmp_path)
    project_config = tmp_path / "config" / "mcporter.json"
    project_config.parent.mkdir(parents=True)
    project_config.write_text("{not-json", encoding="utf-8")

    assert inspect_mcporter_config(scope="home").server_names == frozenset()


def test_home_scope_rejects_an_explicit_single_layer(
    monkeypatch, tmp_path, isolated_home
):
    """MCPORTER_CONFIG replaces the home layer, so a home write cannot satisfy it."""
    monkeypatch.chdir(tmp_path)
    _write_config(
        tmp_path / "explicit.json",
        {"explicit-only": {"command": "explicit"}},
    )
    monkeypatch.setenv("MCPORTER_CONFIG", "explicit.json")

    with pytest.raises(McporterConfigError, match="MCPORTER_CONFIG"):
        inspect_mcporter_config(scope="home")


def test_machine_output_parser_remains_available_for_cleanup_flows():
    output = json.dumps(
        {
            "servers": [
                {"name": "Exa", "baseUrl": "https://example.test"},
                {"name": "linkedin-scraper"},
            ]
        }
    )

    assert configured_server_names(output) == {"exa", "linkedin-scraper"}

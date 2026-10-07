"""Doctor inspects the same comment/trailing-comma syntax as mcporter."""

from __future__ import annotations

import json

import pytest

from agent_reach.channels.mcporter import McporterConfigError, inspect_mcporter_config


@pytest.mark.parametrize("location", ["home", "project", "explicit"])
def test_valid_jsonc_layers_are_inspected(monkeypatch, tmp_path, isolated_home, location):
    monkeypatch.chdir(tmp_path)
    if location == "home":
        path = isolated_home / ".mcporter" / "mcporter.jsonc"
    elif location == "project":
        path = tmp_path / "config" / "mcporter.json"
    else:
        path = tmp_path / "explicit.jsonc"
        monkeypatch.setenv("MCPORTER_CONFIG", str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = """{
      // This is accepted by mcporter even with a .json extension.
      "mcpServers": {
        "Exa": {"baseUrl": "https://mcp.exa.ai/mcp?label=/*keep*/,//keep",},
      },
      /* metadata-only: do not import editor credentials */
      "imports": [],
    }"""
    path.write_text(raw, encoding="utf-8")
    before = path.read_bytes()

    inspection = inspect_mcporter_config()

    assert inspection.server_names == {"exa"}
    assert inspection.source == location
    assert inspection.imports_unchecked is False
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "raw",
    [
        '{"mcpServers": {/* unterminated}',
        '{"mcpServers": {}, "imports": [,,]}',
        '{"mcpServers": {"exa": {"port": 1/*gap*/2}}, "imports": []}',
        "{'mcpServers': {}, 'imports': []}",
        '{mcpServers: {}, "imports": []}',
    ],
)
def test_comments_do_not_relax_other_json_syntax(monkeypatch, tmp_path, raw):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "explicit.jsonc"
    path.write_text(raw, encoding="utf-8")
    monkeypatch.setenv("MCPORTER_CONFIG", str(path))
    with pytest.raises(McporterConfigError, match="UTF-8 JSON"):
        inspect_mcporter_config()


def test_comment_delimiters_and_escaped_quotes_in_strings_are_preserved(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "explicit.jsonc"
    names = [r"back\\slash", "slash//name", "block/*name*/", "comma,}", 'escaped"//name']
    path.write_text(
        json.dumps({"mcpServers": {n: {"command": "x"} for n in names}, "imports": []}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MCPORTER_CONFIG", str(path))
    assert inspect_mcporter_config().server_names == set(names)


@pytest.mark.parametrize(
    "raw",
    [
        '{"mcpServers": {/* comment */ "exa": {"command": "cmd",},}, "imports": ["cursor",],}',
        '{\r\n/* 注释 */\r\n"mcpServers": {"日本語": {"command": "cmd"}}, // end\r\n"imports": []\r\n}',
        '{"mcpServers": {"exa": {"command": "cmd"}}, "imports": []}',
    ],
)
def test_jsonc_arrays_unicode_and_plain_json(monkeypatch, tmp_path, raw):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "explicit.jsonc"
    path.write_text(raw, encoding="utf-8")
    monkeypatch.setenv("MCPORTER_CONFIG", str(path))
    inspection = inspect_mcporter_config()
    assert inspection.server_names in ({"exa"}, {"日本語"})
    assert inspection.imports_unchecked == ("cursor" in raw)


@pytest.mark.parametrize(
    "raw",
    [
        '{"mcpServers": {"exa": {"command": "unterminated}}, "imports": []}',
        '{"mcpServers": {} /* unterminated block comment',
    ],
)
def test_unterminated_strings_and_comments_remain_errors(monkeypatch, tmp_path, raw):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "explicit.jsonc"
    path.write_text(raw, encoding="utf-8")
    monkeypatch.setenv("MCPORTER_CONFIG", str(path))
    with pytest.raises(McporterConfigError, match="UTF-8 JSON"):
        inspect_mcporter_config()


@pytest.mark.parametrize(
    "raw",
    [
        '{"mcpServers": {,}, "imports": []}',
        '{"mcpServers": {}, "imports": [,]}',
        '{"mcpServers": { /* no member */ , }, "imports": []}',
        '{"mcpServers": {}, "imports": [ /* no value */ , ]}',
        '{"mcpServers": {"exa": ,}, "imports": []}',
        '{"mcpServers": {}, "imports": ["cursor",,]}',
    ],
)
def test_invalid_empty_or_missing_value_commas_remain_errors(monkeypatch, tmp_path, raw):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "explicit.jsonc"
    path.write_text(raw, encoding="utf-8")
    monkeypatch.setenv("MCPORTER_CONFIG", str(path))
    with pytest.raises(McporterConfigError, match="UTF-8 JSON"):
        inspect_mcporter_config()

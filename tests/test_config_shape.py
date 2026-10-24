"""Malformed config shapes fail before they can be mistaken for empty settings."""

import pytest

from agent_reach.config import Config, ConfigError


@pytest.mark.parametrize("payload", ["[]", "false", "0", "''"])
def test_falsy_non_mapping_config_is_rejected_without_changing_file(tmp_path, payload):
    path = tmp_path / "config.yaml"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ConfigError):
        Config(path)
    assert path.read_text(encoding="utf-8") == payload


@pytest.mark.parametrize("payload", ["1: value", "true: value", "null: value"])
def test_non_string_config_keys_are_rejected_at_load(tmp_path, payload):
    path = tmp_path / "config.yaml"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ConfigError):
        Config(path)
    assert path.read_text(encoding="utf-8") == payload


@pytest.mark.parametrize("payload", ["", "# only a comment\n", "null", "{}"])
def test_empty_config_still_loads_as_an_empty_mapping(tmp_path, payload):
    path = tmp_path / "config.yaml"
    path.write_text(payload, encoding="utf-8")
    assert Config(path).data == {}

import json

import pytest

from agent_reach.runtime import state


@pytest.mark.parametrize("raw_json", ["null", "[]", '["unexpected"]', "42", "true", '"unexpected"'])
def test_non_object_ledger_recovers_without_rewriting_it(raw_json):
    path = state.state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw_json, encoding="utf-8")
    saved = state.load()
    assert saved["version"] == state.STATE_VERSION
    assert saved["channels"] == {}
    assert saved["skill"]["links"] == []
    assert path.read_text(encoding="utf-8") == raw_json


def test_valid_ledger_keeps_channel_and_extension_data():
    data = {
        "channels": {"reddit": {"added_at": "2026-11-01T00:00:00Z"}},
        "skill": {"links": [{"agent": "custom"}], "unlinked": ["custom-skills"]},
        "custom": [1, 2],
    }
    path = state.state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    saved = state.load()
    assert saved["channels"] == data["channels"]
    assert saved["skill"] == data["skill"]
    assert saved["custom"] == data["custom"]


@pytest.mark.parametrize("skill", [None, [], "unexpected", 42, True])
def test_non_object_skill_metadata_recovers_without_rewriting_it(skill):
    data = {
        "channels": {"reddit": {"added_at": "2026-11-01T00:00:00Z"}},
        "skill": skill,
        "custom": [1, 2],
    }
    raw = json.dumps(data)
    path = state.state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw, encoding="utf-8")

    saved = state.load()

    assert saved["skill"] == {"links": [], "unlinked": []}
    assert saved["channels"] == data["channels"]
    assert saved["custom"] == data["custom"]
    assert path.read_text(encoding="utf-8") == raw


def test_missing_ledger_still_loads_defaults():
    assert state.load()["channels"] == {}


def test_invalid_json_still_loads_defaults():
    path = state.state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken", encoding="utf-8")
    assert state.load()["channels"] == {}

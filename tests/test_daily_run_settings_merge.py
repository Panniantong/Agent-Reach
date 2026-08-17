# -*- coding: utf-8
"""Tests for daily_run settings merge behavior."""

from __future__ import annotations

import json

from agent_reach.daily_run.settings import _merge_repo_defaults


def test_merge_repo_defaults_fills_redfox_block(tmp_path):
    user = tmp_path / "user.json"
    user.write_text(json.dumps({"version": "1.0.0", "mss_weights": {"fx": 0.2}}), encoding="utf-8")
    repo = tmp_path / "repo.json"
    repo.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "mss_weights": {"fx": 0.2, "flow": 0.2, "global": 0.15, "sentiment": 0.15},
                "thresholds": {
                    "macro_veto": 40,
                    "aggressive_entry": 50,
                    "max_snapshot_age_hours": 24,
                },
                "redfox": {"enabled": False, "cache_ttl_seconds": 3600},
            }
        ),
        encoding="utf-8",
    )
    import agent_reach.daily_run.settings as settings_mod

    old = settings_mod._DEFAULT_PATH
    settings_mod._DEFAULT_PATH = repo
    try:
        merged = _merge_repo_defaults(json.loads(user.read_text()), user)
    finally:
        settings_mod._DEFAULT_PATH = old
    assert merged["redfox"]["enabled"] is False
    assert merged["redfox"]["cache_ttl_seconds"] == 3600

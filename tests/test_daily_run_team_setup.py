# -*- coding: utf-8
"""Tests for Team-First one-click setup."""

from __future__ import annotations

import json

import agent_reach.daily_run.settings as settings_mod
from agent_reach.daily_run.settings import clear_settings_cache
from agent_reach.daily_run.team_setup import enable_team_first, render_team_setup_markdown


def test_enable_team_first_writes_user_settings(tmp_path, monkeypatch):
    repo = tmp_path / "repo.json"
    repo.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "mss_weights": {
                    "fx": 0.2,
                    "flow": 0.2,
                    "global": 0.15,
                    "sentiment": 0.15,
                    "technical": 0.15,
                    "quant": 0.1,
                    "risk": 0.05,
                },
                "thresholds": {"max_snapshot_age_hours": 24},
                "team": {"enabled": False, "morning_team_first": False, "close_team_first": False},
            }
        ),
        encoding="utf-8",
    )
    user = tmp_path / "user.json"
    user.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "mss_weights": {
                    "fx": 0.2,
                    "flow": 0.2,
                    "global": 0.15,
                    "sentiment": 0.15,
                    "technical": 0.15,
                    "quant": 0.1,
                    "risk": 0.05,
                },
                "thresholds": {"max_snapshot_age_hours": 24},
                "team": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )

    old_default = settings_mod._DEFAULT_PATH
    old_user = settings_mod._USER_PATH
    settings_mod._DEFAULT_PATH = repo
    settings_mod._USER_PATH = user
    clear_settings_cache()
    try:
        dry = enable_team_first(path=user, dry_run=True)
        assert dry["changed"]
        assert "team.enabled=True" in dry["changed"][0]

        result = enable_team_first(path=user)
        assert result["saved"] is True
        saved = json.loads(user.read_text(encoding="utf-8"))
        assert saved["team"]["enabled"] is True
        assert saved["team"]["morning_team_first"] is True
        assert saved["team"]["close_team_first"] is True

        again = enable_team_first(path=user)
        assert again["changed"] == []
        assert "无需变更" in again["message"]
    finally:
        settings_mod._DEFAULT_PATH = old_default
        settings_mod._USER_PATH = old_user
        clear_settings_cache()


def test_render_team_setup_markdown():
    md = render_team_setup_markdown(
        {
            "path": "/tmp/settings.json",
            "message": "已启用 Team-First（3 项）",
            "changed": ["team.enabled=True", "team.morning_team_first=True"],
            "team": {"enabled": True, "morning_team_first": True, "close_team_first": True},
        }
    )
    assert "Team-First" in md
    assert "team.enabled=True" in md

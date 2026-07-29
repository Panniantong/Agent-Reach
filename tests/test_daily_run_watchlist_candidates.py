# -*- coding: utf-8
"""Tests for weekly hot-sector watchlist candidates."""

import json

import pytest

from agent_reach.daily_run.settings import load_settings
from agent_reach.daily_run.watchlist_candidates import (
    build_weekly_watchlist_candidates,
    effective_watchlist_candidates,
    save_weekly_candidates,
    update_candidates_from_weekly,
    weekly_candidates_path,
)


@pytest.fixture
def settings():
    cfg = load_settings()
    cfg.setdefault("watchlist", {})
    cfg["watchlist"]["weekly_candidates_enabled"] = True
    cfg["watchlist"]["weekly_candidates_max"] = 4
    cfg["watchlist"]["weekly_hot_sector_limit"] = 2
    cfg["watchlist"]["sector_pools"] = {
        "半导体": [
            {"code": "688008", "name": "澜起科技", "keywords": ["澜起", "半导体"]},
            {"code": "688981", "name": "中芯国际", "keywords": ["中芯", "半导体"]},
        ],
        "光通信": [
            {"code": "300308", "name": "中际旭创", "keywords": ["中际", "光模块"]},
        ],
    }
    cfg["watchlist"]["candidates"] = [
        {"code": "603986", "name": "兆易创新", "keywords": ["兆易"]},
    ]
    return cfg


def _weekly_report():
    return {
        "week_end": "2026-07-25",
        "holdings": [{"code": "688008", "name": "澜起科技"}],
        "hot_sectors": [
            {
                "code": "300308",
                "name": "中际旭创",
                "sector": "光通信",
                "change_pct": 5.2,
            },
        ],
        "sector_groups": {
            "半导体": [
                {"code": "603986", "name": "兆易创新", "change_pct": 3.5},
                {"code": "688012", "name": "中微公司", "change_pct": 2.1},
            ],
            "光通信": [
                {"code": "300308", "name": "中际旭创", "change_pct": 5.2},
            ],
        },
        "sector_research": [{"label": "半导体 板块", "success": True}],
    }


class TestWatchlistCandidates:
    def test_build_from_hot_sectors(self, settings):
        update = build_weekly_watchlist_candidates(_weekly_report(), settings)
        codes = {c["code"] for c in update.candidates}
        assert "688981" in codes or "688008" in codes
        assert "300308" in codes
        assert all(c.get("reason") for c in update.candidates)
        assert update.sectors

    def test_effective_merge_static_and_weekly(self, settings, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.watchlist_candidates.weekly_candidates_path",
            lambda: tmp_path / "weekly.json",
        )
        save_weekly_candidates(
            {
                "week_end": "2026-07-25",
                "candidates": [
                    {
                        "code": "688981",
                        "name": "中芯国际",
                        "keywords": ["中芯"],
                        "reason": "本周热点板块：半导体",
                    }
                ],
            }
        )
        merged = effective_watchlist_candidates(settings)
        codes = [c["code"] for c in merged]
        assert "603986" in codes
        assert "688981" in codes

    def test_update_persists_file(self, settings, tmp_path, monkeypatch):
        path = tmp_path / "weekly.json"
        monkeypatch.setattr(
            "agent_reach.daily_run.watchlist_candidates.weekly_candidates_path",
            lambda: path,
        )
        record = update_candidates_from_weekly(_weekly_report(), settings)
        assert path.exists()
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["candidates"]
        assert record["message"]

    def test_skips_held_and_static_codes(self, settings):
        update = build_weekly_watchlist_candidates(_weekly_report(), settings)
        codes = {c["code"] for c in update.candidates}
        assert "688008" not in codes
        assert "603986" not in codes

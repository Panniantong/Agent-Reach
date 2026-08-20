# -*- coding: utf-8
"""Tests for expert enable/disable toggles."""

from agent_reach.daily_run.plugins.loader import MSS_EXPERT_NAMES, run_experts
from agent_reach.daily_run.settings import load_settings
from agent_reach.daily_run.team import (
    expert_card_enabled,
    experts_enabled,
    mss_experts_enabled,
    team_first_enabled,
)


def _base_snapshot(**overrides):
    snap = {
        "code": "688008",
        "name": "澜起科技",
        "mss_breakdown": {"fx": 35, "flow": 48, "global": 38, "sentiment": 50},
        "portfolio": {
            "total": 100000,
            "cash_ratio": 0.61,
            "holdings": [
                {"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87},
                {"code": "002583", "name": "海能达", "shares": 500, "cost": 12.5, "unrealized_pnl": -11400},
            ],
        },
    }
    snap.update(overrides)
    return snap


class TestExpertsToggle:
    def test_disabled_by_default_in_config(self):
        cfg = load_settings()
        assert cfg.get("team", {}).get("enabled") is False
        assert experts_enabled(cfg, workflow="morning") is False
        assert expert_card_enabled(cfg, workflow="morning") is False
        assert experts_enabled(cfg, workflow="close") is False
        assert experts_enabled(cfg, workflow="intraday") is False

    def test_mss_experts_without_full_team(self):
        cfg = load_settings()
        cfg = {
            **cfg,
            "team": {
                **(cfg.get("team") or {}),
                "enabled": False,
                "mss_experts": True,
                "morning_mss_experts": True,
                "intraday_mss_experts": True,
            },
        }
        assert mss_experts_enabled(cfg, workflow="morning") is True
        assert mss_experts_enabled(cfg, workflow="intraday") is True
        assert expert_card_enabled(cfg, workflow="morning") is False

    def test_enabled_when_team_on(self):
        cfg = load_settings()
        cfg = {
            **cfg,
            "team": {
                **(cfg.get("team") or {}),
                "enabled": True,
                "morning_team_first": True,
                "close_team_first": True,
                "intraday_experts": True,
            },
        }
        assert experts_enabled(cfg, workflow="morning") is True
        assert expert_card_enabled(cfg, workflow="morning") is True
        assert team_first_enabled(cfg, workflow="morning") is True


class TestMssExpertsDifferentiation:
    def test_per_symbol_mss_differs_with_mss_experts(self):
        cfg = load_settings()
        snap_a = run_experts(
            _base_snapshot(price=255.87, change_pct=1.5),
            cfg,
            names=MSS_EXPERT_NAMES,
        )
        snap_b = run_experts(
            _base_snapshot(
                code="002583",
                name="海能达",
                price=10.2,
                change_pct=-3.5,
                unrealized_pnl=-11400,
            ),
            cfg,
            names=MSS_EXPERT_NAMES,
        )
        assert snap_a["mss_final"] != snap_b["mss_final"]
        assert "technical" in (snap_a.get("mss_breakdown") or {})
        assert "risk" in (snap_b.get("mss_breakdown") or {})

    def test_intraday_price_moves_change_mss_with_same_macro(self):
        cfg = load_settings()
        base = {
            "ma20": 255.0,
            "position_20d": 0.52,
            "volume_ratio": 1.1,
        }
        snap_low = run_experts(
            _base_snapshot(price=252.0, change_pct=0.5, **base),
            cfg,
            names=MSS_EXPERT_NAMES,
        )
        snap_high = run_experts(
            _base_snapshot(price=262.0, change_pct=2.5, **base),
            cfg,
            names=MSS_EXPERT_NAMES,
        )
        assert snap_low["mss_final"] != snap_high["mss_final"]
        assert snap_high["mss_final"] > snap_low["mss_final"]

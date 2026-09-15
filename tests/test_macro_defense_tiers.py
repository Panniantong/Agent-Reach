# -*- coding: utf-8 -*-
"""Tests for tiered macro MSS defense (P2)."""

from agent_reach.daily_run.macro_defense_tiers import (
    apply_macro_defense_tiers,
    build_weekly_observe_bump_evidence,
    count_severe_tier_days,
)


def test_severe_defense_caps():
    merged = {"deploy_ratio": 1.0, "max_position_pct": 80.0, "macro_veto": 40.0}
    result = apply_macro_defense_tiers(merged, mss=28.0, settings={"macro_defense_tiers": {"enabled": True}})
    assert result["applied"] is True
    assert result["tier"] == "severe"
    assert merged["deploy_ratio"] == 0.25
    assert merged["max_position_pct"] == 40.0


def test_mild_defense_caps():
    merged = {"deploy_ratio": 1.0, "max_position_pct": 80.0, "macro_veto": 40.0}
    result = apply_macro_defense_tiers(merged, mss=35.0, settings={"macro_defense_tiers": {"enabled": True}})
    assert result["applied"] is True
    assert result["tier"] == "mild"
    assert merged["deploy_ratio"] == 0.45
    assert merged["max_position_pct"] == 60.0


def test_count_severe_tier_days_empty_week():
    stats = count_severe_tier_days("2099-01-06", "2099-01-10", settings={"macro_defense_tiers": {"enabled": True}})
    assert stats["severe_day_count"] == 0


def test_build_weekly_observe_bump_skips_when_below_threshold(monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.macro_defense_tiers.count_severe_tier_days",
        lambda *_a, **_k: {"severe_day_count": 1, "severe_days": ["2026-09-11"]},
    )
    out = build_weekly_observe_bump_evidence(
        {"week_start": "2026-09-07", "week_end": "2026-09-11"},
        settings={"macro_defense_tiers": {"enabled": True, "observe_weekly_trigger_max": 3}},
    )
    assert out.get("skipped") is True


def test_build_weekly_observe_bump_evidence_when_triggered(monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.macro_defense_tiers.count_severe_tier_days",
        lambda *_a, **_k: {
            "severe_day_count": 3,
            "severe_days": ["2026-09-08", "2026-09-09", "2026-09-10"],
        },
    )
    monkeypatch.setattr(
        "agent_reach.daily_run.harness_policy.macro_veto_default",
        lambda _s: 30.0,
    )
    out = build_weekly_observe_bump_evidence(
        {"week_start": "2026-09-07", "week_end": "2026-09-11"},
        settings={
            "macro_defense_tiers": {
                "enabled": True,
                "observe_weekly_trigger_max": 3,
                "observe_bump_to_mild": 35.0,
            },
            "thresholds": {"macro_veto": 30.0},
        },
    )
    assert out.get("skipped") is not True
    assert out["policy"]
    assert "35" in out["policy"][0]

# -*- coding: utf-8
"""Tests for tiered macro MSS defense (P2)."""

from agent_reach.daily_run.macro_defense_tiers import apply_macro_defense_tiers


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

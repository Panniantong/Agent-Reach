# -*- coding: utf-8
"""Tests for Xueqiu hit-rate driven candidate overlay."""

from unittest.mock import patch

from agent_reach.daily_run.harness_policy import apply_harness_policy_overlay
from agent_reach.daily_run.xueqiu_hit_candidate_policy import (
    apply_xueqiu_hit_candidate_overlay,
    resolve_xueqiu_hit_candidate_overlay,
)


def test_overlay_skipped_when_hit_rate_ok():
    settings = {
        "macro_collector": {
            "xueqiu_hit_candidate_overlay_enabled": True,
            "portfolio_hot_stock_boost": 2,
        },
        "watchlist": {"weekly_candidates_max": 10},
    }
    with patch(
        "agent_reach.daily_run.xueqiu_hit_candidate_policy.summarize_xueqiu_hit_outcomes",
        return_value={"total": 8, "hit_rate": 0.625, "misses": 2},
    ):
        out, meta = resolve_xueqiu_hit_candidate_overlay(settings)
    assert meta == {}
    assert out["macro_collector"]["portfolio_hot_stock_boost"] == 2


def test_overlay_defensive_when_hit_rate_low():
    settings = {
        "macro_collector": {
            "xueqiu_hit_candidate_overlay_enabled": True,
            "portfolio_hot_stock_boost": 2,
            "xueqiu_hit_low_rate": 0.4,
            "xueqiu_hit_overlay_min_samples": 3,
            "xueqiu_hit_overlay_min_misses": 3,
        },
        "watchlist": {
            "weekly_candidates_max": 10,
            "weekly_candidates_min": 5,
            "xueqiu_hot_candidates_enabled": True,
            "eastmoney_screen_candidates_enabled": True,
        },
        "experience": {"enabled": True},
    }
    with patch(
        "agent_reach.daily_run.xueqiu_hit_candidate_policy.summarize_xueqiu_hit_outcomes",
        return_value={"total": 6, "hit_rate": 0.25, "misses": 4},
    ):
        out, meta = apply_xueqiu_hit_candidate_overlay(settings)
    assert meta["mode"] == "defensive"
    assert out["macro_collector"]["portfolio_hot_stock_boost"] == 1.0
    assert out["watchlist"]["xueqiu_hot_candidates_enabled"] is False
    assert out["watchlist"]["eastmoney_screen_candidates_enabled"] is False
    assert out["watchlist"]["weekly_candidates_max"] == 8


def test_overlay_offensive_when_hit_rate_high():
    settings = {
        "macro_collector": {
            "xueqiu_hit_candidate_overlay_enabled": True,
            "portfolio_hot_stock_boost": 2,
            "xueqiu_hit_high_rate": 0.6,
            "xueqiu_hit_overlay_min_samples": 3,
            "xueqiu_hit_overlay_min_hits": 3,
        },
        "watchlist": {
            "weekly_candidates_max": 10,
            "xueqiu_hot_candidates_enabled": False,
            "eastmoney_screen_candidates_enabled": False,
        },
        "experience": {"enabled": True},
    }
    with patch(
        "agent_reach.daily_run.xueqiu_hit_candidate_policy.summarize_xueqiu_hit_outcomes",
        return_value={"total": 8, "hit_rate": 0.75, "hits": 6, "misses": 2},
    ):
        out, meta = apply_xueqiu_hit_candidate_overlay(settings)
    assert meta["mode"] == "offensive"
    assert out["macro_collector"]["portfolio_hot_stock_boost"] == 3.0
    assert out["watchlist"]["xueqiu_hot_candidates_enabled"] is True
    assert out["watchlist"]["weekly_candidates_max"] == 11


@patch("agent_reach.daily_run.harness_policy._overlay_enabled", return_value=True)
@patch("agent_reach.daily_run.harness.load_harness", return_value={"memory": [], "policy": []})
def test_apply_harness_policy_includes_hit_candidate_meta(mock_load, mock_overlay):
    settings = {
        "harness": {"enabled": True},
        "thresholds": {},
        "macro_collector": {
            "xueqiu_hit_candidate_overlay_enabled": True,
            "portfolio_hot_stock_boost": 2,
        },
        "watchlist": {"weekly_candidates_max": 10, "weekly_candidates_min": 5},
        "experience": {"enabled": True},
    }
    with patch(
        "agent_reach.daily_run.xueqiu_hit_candidate_policy.summarize_xueqiu_hit_outcomes",
        return_value={"total": 5, "hit_rate": 0.2, "misses": 4},
    ):
        eff = apply_harness_policy_overlay(settings)
    overlay = (eff.get("harness_runtime") or {}).get("xueqiu_hit_candidate_overlay") or {}
    assert overlay.get("mode") == "defensive"
    assert eff["macro_collector"]["portfolio_hot_stock_boost"] == 1.0

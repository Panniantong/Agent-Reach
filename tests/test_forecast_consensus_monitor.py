# -*- coding: utf-8
"""Tests for model homogeneity warning (P2)."""

from agent_reach.daily_run.forecast_consensus_monitor import build_homogeneity_warning


def test_homogeneous_bearish_warning():
    forecast = {
        "symbols": {
            "688008": {"role": "holding", "name": "澜起", "model_votes": {"bull": 0, "bear": 2}},
            "002583": {"role": "holding", "name": "海能达", "model_votes": {"bull": 0, "bear": 2}},
            "000725": {"role": "holding", "name": "京东方", "model_votes": {"bull": 0, "bear": 2}},
        }
    }
    warn = build_homogeneity_warning(forecast, settings={"forecast_consensus": {"homogeneity_warn_min_symbols": 3}})
    assert warn is not None
    assert warn["kind"] == "homogeneous_bearish"
    assert warn["count"] == 3

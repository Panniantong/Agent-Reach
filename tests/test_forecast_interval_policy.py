# -*- coding: utf-8
"""Tests for ATR interval + accuracy guard (P0/P3)."""

from unittest.mock import patch

from agent_reach.daily_run.forecast_interval_policy import (
    apply_symbol_interval_policy,
    atr_pct_band,
    interval_width_scale,
    should_trigger_forecast_calibrate,
)


def test_atr_pct_band_scales_with_atr():
    lo, hi, width, meta = atr_pct_band(
        base_price=100.0,
        mid_pct=0.0,
        atr=2.0,
        settings={"forecast_interval": {"atr_multiplier": 2.0, "min_width_pct": 2.0, "max_width_pct": 20.0}},
    )
    assert meta["method"] == "atr"
    assert width == round(hi - lo, 2)
    assert width >= 2.0


def test_interval_width_scale_widens_on_low_hit_rate():
    with patch(
        "agent_reach.daily_run.forecast_interval_policy.recent_weekly_symbol_hit_rates",
        return_value=[45.0, 48.0],
    ):
        scale, notes = interval_width_scale(
            settings={
                "forecast_interval": {
                    "convergence_low_hit_pct": 50.0,
                    "convergence_widen_factor": 1.1,
                }
            }
        )
    assert scale > 1.0
    assert notes


def test_should_trigger_forecast_calibrate():
    with patch(
        "agent_reach.daily_run.forecast_interval_policy.recent_weekly_symbol_hit_rates",
        return_value=[55.0, 58.0, 60.0],
    ):
        assert should_trigger_forecast_calibrate(
            settings={"forecast_interval": {"accuracy_calibrate_threshold_pct": 60.0, "accuracy_calibrate_weeks": 2}}
        )


def test_apply_symbol_interval_policy_uses_atr_when_present():
    lo, hi, width, meta = apply_symbol_interval_policy(
        lo=-5.0,
        hi=5.0,
        mid=0.0,
        base_price=10.0,
        code="002583",
        enriched={"atr14": 0.15},
        settings={"forecast_interval": {"enabled": True, "atr_multiplier": 2.0}},
    )
    assert meta.get("method") == "atr"
    assert hi - lo <= 15.0

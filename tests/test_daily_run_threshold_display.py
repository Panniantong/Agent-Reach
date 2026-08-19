# -*- coding: utf-8
"""Threshold ref display uses harness-effective values."""

from unittest.mock import patch

import pytest

from agent_reach.daily_run.harness_display import (
    apply_threshold_refs,
    format_effective_thresholds_markdown,
    format_lookback_overlay_markdown,
    format_lookback_weights_pct,
    format_mss_breakdown_lines,
    threshold_refs_for_display,
)
from agent_reach.daily_run.pipeline import _format_mss_breakdown_lines


@pytest.fixture
def portfolio():
    return {
        "holdings": [{"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87}],
        "watchlist": [],
    }


class TestThresholdDisplay:
    @patch("agent_reach.daily_run.harness_display.threshold_refs_for_display")
    def test_apply_threshold_refs_overwrites_cache(self, mock_refs):
        mock_refs.return_value = {
            "_macro_veto_ref": 30.0,
            "_aggressive_ref": 45.0,
            "_min_cash_ratio_ref": 0.5,
        }
        out = apply_threshold_refs(
            {
                "fx": 51.0,
                "_aggressive_ref": 50.0,
                "_macro_veto_ref": 40.0,
                "_min_cash_ratio_ref": 0.0,
            },
            {},
        )
        assert out["fx"] == 51.0
        assert out["_aggressive_ref"] == 45.0
        assert out["_macro_veto_ref"] == 30.0
        assert out["_min_cash_ratio_ref"] == 0.5

    def test_format_mss_breakdown_uses_friendly_labels(self):
        lines = format_mss_breakdown_lines(
            {
                "fx": 51.0,
                "_macro_veto_ref": 30.0,
                "_aggressive_ref": 45.0,
                "_min_cash_ratio_ref": 0.5,
                "_max_price_deviation_pct_ref": 0.08,
            }
        )
        assert "- fx: 51.0" in lines
        assert "- 宏观否决线: 30" in lines
        assert "- 进攻阈值: 45" in lines
        assert "- 最低现金比例: 50%" in lines
        assert "- 价格锚点偏差上限: 8%" in lines
        assert not any("_aggressive_ref" in line for line in lines)

    def test_pipeline_wrapper_matches_harness_display(self):
        lines = _format_mss_breakdown_lines(
            {"fx": 51.0, "_aggressive_ref": 45.0, "_macro_veto_ref": 30.0}
        )
        assert "- 进攻阈值: 45" in lines

    @patch("agent_reach.daily_run.settings.effective_settings")
    @patch("agent_reach.daily_run.harness_display._policy_value")
    def test_threshold_refs_for_display_uses_effective_settings(self, mock_policy, mock_effective):
        raw = {"thresholds": {}}
        mock_effective.return_value = raw
        mock_policy.side_effect = lambda _eff, key: {
            "macro_veto": 30.0,
            "aggressive_entry": 45.0,
            "min_cash_ratio": 0.5,
            "max_price_deviation_pct": 0.08,
            "high_position_20d": 0.7,
            "min_volume_ratio": 1.0,
            "max_vwap_deviation_pct": 0.04,
        }[key]

        refs = threshold_refs_for_display(raw)
        mock_effective.assert_called_once()
        assert refs["_aggressive_ref"] == 45.0
        assert refs["_macro_veto_ref"] == 30.0
        assert refs["_min_cash_ratio_ref"] == 0.5

    def test_format_effective_thresholds_markdown(self):
        settings = {
            "harness_runtime": {
                "threshold_overlay": {
                    "aggressive_entry": {"base": 50.0, "effective": 45.0},
                    "macro_veto": {"base": 40.0, "effective": 30.0},
                    "min_cash_ratio": {"base": 0.0, "effective": 0.5},
                }
            }
        }
        md = format_effective_thresholds_markdown(settings)
        assert "策略参数" in md
        assert "进攻阈值: 45" in md
        assert "基准 50" in md
        assert "宏观否决线: 30" in md
        assert "最低现金比例: 50%" in md

    def test_format_lookback_weights_pct(self):
        assert format_lookback_weights_pct([0.6, 0.25, 0.15]) == "60%/25%/15%"

    def test_format_lookback_overlay_markdown(self):
        settings = {
            "harness_runtime": {
                "lookback_overlay": {
                    "lookback_weights": {
                        "base": [0.5, 0.3, 0.2],
                        "effective": [0.6, 0.25, 0.15],
                    }
                }
            }
        }
        md = format_lookback_overlay_markdown(settings)
        assert "Lookback 权重（harness 有效值）" in md
        assert "60%/25%/15%" in md
        assert "基准 50%/30%/20%" in md


class TestVerdictEffectiveThresholds:
    def test_reasoning_uses_harness_effective_aggressive(self):
        from agent_reach.daily_run.settings import effective_settings, load_settings
        from agent_reach.daily_run.verdict import compute_verdict

        settings = load_settings()
        eff = effective_settings(settings)
        aggressive = float((eff.get("thresholds") or {}).get("aggressive_entry", 50))
        snap = {
            "code": "688008",
            "name": "澜起科技",
            "price": 255.87,
            "ma20": 260.0,
            "position_20d": 0.55,
            "volume_ratio": 1.2,
            "mss_final": aggressive - 2,
            "structured_review_complete": True,
        }
        v = compute_verdict(snap, settings)
        assert f"{aggressive:.0f}" in v.reasoning
        assert "50" not in v.reasoning or f"{aggressive:.0f}" == "50"

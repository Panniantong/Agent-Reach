# -*- coding: utf-8
"""Threshold ref display uses harness-effective values."""

from unittest.mock import patch

import pytest

from agent_reach.daily_run.macro_collector import apply_threshold_refs, threshold_refs_for_display
from agent_reach.daily_run.pipeline import _format_mss_breakdown_lines


@pytest.fixture
def portfolio():
    return {
        "holdings": [{"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87}],
        "watchlist": [],
    }


class TestThresholdDisplay:
    @patch("agent_reach.daily_run.macro_collector.threshold_refs_for_display")
    def test_apply_threshold_refs_overwrites_cache(self, mock_refs):
        mock_refs.return_value = {"_macro_veto_ref": 30.0, "_aggressive_ref": 45.0}
        out = apply_threshold_refs(
            {"fx": 51.0, "_aggressive_ref": 50.0, "_macro_veto_ref": 40.0},
            {},
        )
        assert out["fx"] == 51.0
        assert out["_aggressive_ref"] == 45.0
        assert out["_macro_veto_ref"] == 30.0

    def test_format_mss_breakdown_uses_friendly_labels(self):
        lines = _format_mss_breakdown_lines(
            {
                "fx": 51.0,
                "_macro_veto_ref": 30.0,
                "_aggressive_ref": 45.0,
            }
        )
        assert "- fx: 51.0" in lines
        assert "- 宏观否决线: 30" in lines
        assert "- 进攻阈值: 45" in lines
        assert not any("_aggressive_ref" in line for line in lines)

    @patch("agent_reach.daily_run.settings.effective_settings")
    @patch("agent_reach.daily_run.harness_policy.macro_veto_default", return_value=30.0)
    @patch("agent_reach.daily_run.harness_policy.aggressive_entry_default", return_value=45.0)
    def test_threshold_refs_for_display_uses_effective_settings(
        self,
        mock_aggressive,
        mock_macro,
        mock_effective,
    ):
        raw = {"thresholds": {}}
        mock_effective.return_value = raw
        refs = threshold_refs_for_display(raw)
        mock_effective.assert_called_once()
        assert refs == {"_macro_veto_ref": 30.0, "_aggressive_ref": 45.0}
        mock_macro.assert_called_once_with(raw)
        mock_aggressive.assert_called_once_with(raw)

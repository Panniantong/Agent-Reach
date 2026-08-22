# -*- coding: utf-8
"""Tests for close P&L factor attribution."""

from agent_reach.daily_run.backtest_attributor import (
    build_close_pnl_attribution,
    render_close_pnl_attribution_markdown,
)


def test_build_close_pnl_attribution():
    attr = build_close_pnl_attribution(
        {
            "daily_pnl": 1200.0,
            "realized_pnl": 300.0,
            "holdings": [
                {"code": "688008", "day_pnl": 800.0},
                {"code": "603986", "day_pnl": 100.0},
            ],
        },
        snapshot={"mss_final": 55.0, "mss_breakdown": {"_emotion_fusion_ref": {"rating": "强", "score": 5}}},
        baseline={"mss_final": 50.0},
    )
    assert attr["held_day_pnl"] == 900.0
    assert attr["rebalance_pnl"] == 0.0
    assert attr["mss_delta"] == 5.0
    md = render_close_pnl_attribution_markdown(attr)
    assert "盈亏因子分解" in md
    assert "现持仓价格" in md


def test_render_close_pnl_attribution_empty_when_no_data():
    assert render_close_pnl_attribution_markdown({}) == ""

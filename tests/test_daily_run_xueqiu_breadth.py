# -*- coding: utf-8
"""Tests for Xueqiu market breadth fallback."""

from unittest.mock import patch

from agent_reach.daily_run.market_breadth_collector import analyze_emotion_from_counts
from agent_reach.daily_run.xueqiu_breadth_collector import fetch_xueqiu_market_breadth


class TestXueqiuBreadth:
    @patch("agent_reach.daily_run.xueqiu_breadth_collector.fetch_xueqiu_index_breadth")
    def test_fetch_xueqiu_market_breadth_sums_sh_sz(self, mock_index):
        mock_index.side_effect = [
            {"symbol": "SH000001", "name": "上证指数", "rise_count": 100, "fall_count": 40, "flat_count": 5},
            {"symbol": "SZ399001", "name": "深证成指", "rise_count": 200, "fall_count": 60, "flat_count": 8},
        ]
        out = fetch_xueqiu_market_breadth()
        assert out["up_count"] == 300
        assert out["down_count"] == 100
        assert out["flat_count"] == 13
        assert out["source"] == "xueqiu"

    def test_analyze_emotion_from_counts_skips_limit_scoring(self):
        em = analyze_emotion_from_counts(3000, 1000, 50, {"net_yi": 20})
        assert em.up_count == 3000
        assert em.limit_up == 0
        assert any("Eastmoney clist" in w for w in em.warnings)

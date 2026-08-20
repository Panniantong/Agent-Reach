# -*- coding: utf-8
"""Tests for akshare limit pool fallback."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from agent_reach.daily_run.limit_pool_collector import fetch_akshare_limit_pools
from agent_reach.daily_run.market_breadth_collector import (
    analyze_emotion_from_counts,
    enrich_emotion_with_limit_pools,
)


def _zt_df():
    return pd.DataFrame(
        [
            {
                "代码": "600000",
                "名称": "测试A",
                "涨跌幅": 10.0,
                "所属行业": "半导体",
            },
            {
                "代码": "000001",
                "名称": "测试B",
                "涨跌幅": 10.0,
                "所属行业": "半导体",
            },
        ]
    )


def _dt_df():
    return pd.DataFrame([{"代码": "002820", "名称": "测试C", "涨跌幅": -10.0}])


def _zb_df():
    return pd.DataFrame([{"代码": "002900", "名称": "测试D", "涨跌幅": 5.0}])


class TestLimitPoolCollector:
    @patch("agent_reach.daily_run.limit_pool_collector._import_akshare")
    def test_fetch_limit_pools_maps_rows(self, mock_import):
        ak = MagicMock()
        ak.stock_zt_pool_em.return_value = _zt_df()
        ak.stock_zt_pool_dtgc_em.return_value = _dt_df()
        ak.stock_zt_pool_zbgc_em.return_value = _zb_df()
        mock_import.return_value = ak

        pool = fetch_akshare_limit_pools("2026-08-20")
        assert pool["limit_up"] == 2
        assert pool["limit_down"] == 1
        assert pool["broken_count"] == 1
        assert pool["broken_rate"] == pytest.approx(0.3333, abs=0.0001)
        assert len(pool["limit_up_stocks"]) == 2
        assert pool["limit_up_stocks"][0]["industry"] == "半导体"


class TestLimitPoolEmotion:
    def test_enrich_xueqiu_partial_emotion(self):
        base = analyze_emotion_from_counts(3000, 1200, 80, {"net_yi": 5}).to_dict()
        base["breadth_partial"] = True
        pool = {
            "limit_up": 79,
            "limit_down": 12,
            "broken_count": 46,
            "source": "akshare_limit_pools",
        }
        em = enrich_emotion_with_limit_pools(base, pool, {"net_yi": 5})
        assert em.limit_up == 79
        assert em.limit_down == 12
        assert em.broken_count == 46
        assert em.broken_rate == pytest.approx(46 / (79 + 46), rel=1e-3)
        assert not any("涨跌停/炸板率需 Eastmoney clist" in w for w in em.warnings)

    def test_enrich_macro_emotion_keeps_index_reasons(self):
        from agent_reach.daily_run.market_review import _macro_breadth_fallback

        base = _macro_breadth_fallback(
            {"sh000001": {"change_pct": 1.5}},
            {"net_yi": 30.0},
        )
        pool = {"limit_up": 50, "limit_down": 8, "broken_count": 10, "source": "akshare_limit_pools"}
        em = enrich_emotion_with_limit_pools(base, pool, {"net_yi": 30.0})
        assert em.limit_up == 50
        assert any("上证" in r for r in em.reasons)
        assert any("涨停" in r for r in em.reasons)

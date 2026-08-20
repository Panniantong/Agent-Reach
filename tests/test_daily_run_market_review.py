# -*- coding: utf-8
"""Tests for a-stock-review market review collectors."""

from unittest.mock import patch

import pytest

from agent_reach.daily_run.lhb_collector import analyze_lhb
from agent_reach.daily_run.market_breadth_collector import analyze_emotion
from agent_reach.daily_run.market_review import (
    compare_market_review,
    get_or_collect_market_review,
    load_market_review,
    market_review_path,
    render_market_review_markdown,
    save_market_review,
)
from agent_reach.daily_run.sector_mainline import analyze_sectors


def _sample_stocks():
    stocks = []
    for i in range(100):
        pct = 10.0 if i < 5 else 1.0 if i < 60 else -1.0
        stocks.append(
            {
                "code": f"{600000 + i:06d}"[-6:],
                "name": f"S{i}",
                "change_pct": pct,
                "industry": "半导体" if i < 20 else "银行",
                "turnover": 5.0,
            }
        )
    return stocks


class TestMarketBreadth:
    def test_analyze_emotion_strong_market(self):
        stocks = _sample_stocks()
        north = {"net_yi": 60.0}
        em = analyze_emotion(stocks, north)
        assert em.up_count == 60
        assert em.down_count == 40
        assert em.limit_up == 5
        assert em.rating in ("强", "中", "弱")
        assert em.position

    def test_analyze_emotion_weak_when_more_down(self):
        stocks = [{"change_pct": -2, "industry": "X"} for _ in range(80)]
        stocks += [{"change_pct": 1, "industry": "X"} for _ in range(20)]
        em = analyze_emotion(stocks, {"net_yi": -80})
        assert em.rating == "弱"
        assert em.position == "2-3成"


class TestSectorMainline:
    def test_single_mainline(self):
        limit_up = [
            {"code": f"{i:06d}", "name": f"L{i}", "change_pct": 10, "industry": "半导体"}
            for i in range(18)
        ]
        limit_up += [{"code": "999999", "name": "X", "change_pct": 10, "industry": "银行"} for _ in range(3)]
        sa = analyze_sectors(limit_up)
        assert sa.mainline_type == "单主线"
        assert "半导体" in sa.reasoning

    def test_multi_mainline(self):
        limit_up = [{"code": "1", "name": "A", "change_pct": 10, "industry": "A"}]
        sa = analyze_sectors(limit_up)
        assert sa.mainline_type == "多题材轮动"


class TestLHB:
    def test_analyze_lhb_bias(self):
        rows = [
            {"code": "600519", "name": "茅台", "net_buy": 3.0, "buy_amt": 5, "sell_amt": 2},
            {"code": "000001", "name": "平安", "net_buy": -1.0, "buy_amt": 1, "sell_amt": 2},
        ]
        la = analyze_lhb(rows)
        assert la.total_net == pytest.approx(2.0)
        assert "进攻" in la.bias or "均衡" in la.bias


class TestMarketReviewPersistence:
    def test_save_load_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.market_review.market_review_dir",
            lambda: tmp_path,
        )
        review = {
            "date": "2026-08-14",
            "emotion": {"score": 3, "rating": "中", "limit_up": 40},
        }
        save_market_review(review)
        loaded = load_market_review("2026-08-14")
        assert loaded["emotion"]["score"] == 3
        assert market_review_path("2026-08-14").exists()

    def test_compare_yesterday(self):
        current = {
            "emotion": {"limit_up": 50, "score": 4, "rating": "强", "northbound_net_yi": 10}
        }
        yesterday = {
            "date": "2026-08-13",
            "emotion": {"limit_up": 40, "score": 2, "rating": "中", "northbound_net_yi": 5},
        }
        cmp_ = compare_market_review(current, yesterday=yesterday)
        assert cmp_["vs_yesterday"]["limit_up_delta"] == 10
        assert cmp_["vs_yesterday"]["emotion_score_delta"] == 2

    def test_render_markdown_contains_sections(self):
        md = render_market_review_markdown(
            {
                "date": "2026-08-14",
                "emotion": {
                    "rating": "中",
                    "score": 2,
                    "position": "5成",
                    "reasons": ["涨跌比 1.2:1"],
                    "warnings": [],
                    "up_count": 2000,
                    "down_count": 1800,
                    "ratio": "2000:1800",
                    "limit_up": 45,
                    "limit_down": 10,
                    "broken_rate": 0.15,
                    "northbound_net_yi": 12.5,
                },
                "sector_analysis": {
                    "mainline_type": "双主线",
                    "reasoning": "test",
                    "main_sectors": [{"name": "半导体", "limit_up_count": 10, "top_stocks": []}],
                    "ladder": [],
                },
                "lhb_analysis": {"capital_preference": "略偏进攻", "buyers": []},
                "comparison": {},
            }
        )
        assert "全市场复盘" in md
        assert "板块主线" in md
        assert "龙虎榜" in md

    @patch("agent_reach.daily_run.market_review.collect_market_review")
    def test_get_or_collect_uses_cache(self, mock_collect, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.market_review.market_review_dir",
            lambda: tmp_path,
        )
        save_market_review({"date": "2026-08-14", "emotion": {"score": 1}})
        out = get_or_collect_market_review(
            settings={"market_review": {"enabled": True}},
            review_date="2026-08-14",
        )
        assert out["emotion"]["score"] == 1
        mock_collect.assert_not_called()


class TestMarketReviewFallback:
    def test_macro_breadth_fallback_from_indices(self):
        from agent_reach.daily_run.market_review import _macro_breadth_fallback

        em = _macro_breadth_fallback(
            {"sh000001": {"change_pct": 1.5, "name": "上证指数"}},
            {"net_yi": 30.0},
        )
        assert em["breadth_degraded"] is True
        assert em["rating"] in ("强", "中", "弱")
        assert any("上证" in r for r in em["reasons"])

    @patch("agent_reach.daily_run.eastmoney_market.fetch_all_stocks")
    @patch("agent_reach.daily_run.akshare_adapter.fetch_all_a_spot_stocks")
    @patch("agent_reach.daily_run.eastmoney_market.fetch_indices")
    @patch("agent_reach.daily_run.eastmoney_market.fetch_north_flow_resilient")
    @patch("agent_reach.daily_run.eastmoney_market.fetch_lhb")
    def test_collect_uses_akshare_when_em_clist_fails(
        self,
        mock_lhb,
        mock_north,
        mock_indices,
        mock_ak,
        mock_em_stocks,
    ):
        from agent_reach.daily_run.market_review import collect_market_review

        mock_em_stocks.side_effect = RuntimeError("Remote end closed connection")
        mock_ak.return_value = _sample_stocks()
        mock_indices.return_value = {"sh000001": {"change_pct": 0.5, "name": "上证指数"}}
        mock_north.return_value = ({"net_yi": 10.0, "direction": "inflow"}, [])
        mock_lhb.return_value = []

        review = collect_market_review(settings={"market_review": {}}, review_date="2026-08-20")
        assert "error" not in review
        assert review["emotion"]["up_count"] == 60
        assert any("akshare" in w for w in review["warnings"])

    def test_render_degraded_not_full_error(self):
        from agent_reach.daily_run.market_review import _macro_breadth_fallback, render_market_review_markdown

        md = render_market_review_markdown(
            {
                "date": "2026-08-20",
                "indices": {"sh000001": {"name": "上证指数", "change_pct": 0.5, "price": 3000}},
                "emotion": _macro_breadth_fallback(
                    {"sh000001": {"change_pct": 0.5}},
                    {"net_yi": 5},
                ),
                "sector_analysis": {"mainline_type": "多题材轮动", "reasoning": "无涨停样本"},
                "lhb_analysis": {},
                "comparison": {},
                "warnings": ["eastmoney clist: disconnected"],
            }
        )
        assert "市场宽度数据拉取失败" not in md
        assert "降级" in md or "不可用" in md
        assert "全市场复盘" in md

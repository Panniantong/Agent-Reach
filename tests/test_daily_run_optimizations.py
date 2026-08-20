# -*- coding: utf-8
"""Tests for Phase A-E optimizations."""

from unittest.mock import patch

import pytest

from agent_reach.daily_run.curve_analysis import analyze_intraday_curve, render_curve_markdown
from agent_reach.daily_run.mss_forecast import forecast_mss_range
from agent_reach.daily_run.schedule import INTRADAY_MAX_SCANS, INTRADAY_SCAN_TIMES, default_entries
from agent_reach.daily_run.settings import load_settings
from agent_reach.daily_run.verdict import compute_verdict, fuse_verdict_with_team


class TestMssForecast:
    def test_forecast_range(self):
        snap = {"mss_breakdown": {"fx": 35, "flow": 48, "global": 38, "sentiment": 50}}
        rng, meta = forecast_mss_range(snap, load_settings(), simulations=50)
        assert len(rng) == 2
        assert rng[0] <= rng[1]
        assert meta["method"] == "monte_carlo_lite"


class TestCurveAnalysis:
    def test_analyze_intraday_curve(self):
        analysis = analyze_intraday_curve(
            [42, 44, 46, 45],
            predicted_range=(40, 52),
            scan_ids=["S1", "S2", "S3", "S4"],
        )
        assert analysis["points"] == 4
        md = render_curve_markdown(analysis)
        assert "盘中 MSS 曲线" in md
        assert "扫描次数：**4**" in md
        assert "S1=42" in md


class TestVerdictFusion:
    def test_fuse_team_consensus_downgrade(self):
        settings = load_settings()
        snap = {
            "code": "688008",
            "price": 100,
            "ma20": 95,
            "position_20d": 0.5,
            "volume_ratio": 1.2,
            "mss_breakdown": {"fx": 55, "flow": 55, "global": 55, "sentiment": 55},
            "mss_final": 55.0,
            "sources": {"quote": {"summary": "q"}, "flow": {"summary": "f"}, "sentiment": {"summary": "s"}},
            "team_consensus_label": "观察",
            "team_review": {"consensus_score": 45, "consensus_label": "观察"},
        }
        base = compute_verdict(snap, settings)
        fused = fuse_verdict_with_team(base, snap, settings)
        assert fused.verdict == "观察"

    def test_buffett_block(self):
        settings = load_settings()
        snap = {
            "code": "688008",
            "price": 100,
            "ma20": 95,
            "position_20d": 0.5,
            "volume_ratio": 1.2,
            "peg": 2.5,
            "mss_breakdown": {"fx": 55, "flow": 55, "global": 55, "sentiment": 55},
            "sources": {"quote": {"summary": "q"}, "flow": {"summary": "f"}, "sentiment": {"summary": "s"}},
        }
        base = compute_verdict(snap, settings)
        fused = fuse_verdict_with_team(base, snap, settings)
        assert fused.blocked is True


class TestScheduleEntries:
    def test_fifteen_intraday_scans(self):
        assert len(INTRADAY_SCAN_TIMES) == 13
        assert INTRADAY_MAX_SCANS == 15

    def test_default_entries_count(self):
        assert len(default_entries()) == 18  # premarket + morning + 13 scans + close + weekly + forecast


class TestMacroCollector:
    @patch("agent_reach.daily_run.hot_news_collector.collect_hot_news")
    @patch("agent_reach.daily_run.macro_collector._fetch_index_change", return_value=0.5)
    @patch("agent_reach.daily_run.macro_collector._fetch_northbound_flow", return_value=12.0)
    @patch("agent_reach.daily_run.macro_collector._fetch_xueqiu_sentiment", return_value=("雪球热点：存储", []))
    def test_collect_macro_context(self, mock_xq, mock_nb, mock_idx, mock_hot):
        from agent_reach.daily_run.hot_news_collector import HotNewsResult
        from agent_reach.daily_run.macro_collector import collect_macro_context

        mock_hot.return_value = HotNewsResult()
        pf = {"mss_breakdown": {"fx": 50, "flow": 50, "global": 50, "sentiment": 50}}
        ctx = collect_macro_context(pf, settings=load_settings())
        assert "flow" in ctx["sources"]
        assert ctx["mss_breakdown"]["flow"] > 50
        assert "_macro_baseline_ref" in ctx["mss_breakdown"]

    @patch("agent_reach.daily_run.hot_news_collector.collect_hot_news")
    @patch("agent_reach.daily_run.macro_collector._fetch_index_change", return_value=0.0)
    @patch("agent_reach.daily_run.macro_collector._fetch_northbound_flow", return_value=None)
    @patch("agent_reach.daily_run.macro_collector._fetch_xueqiu_sentiment", return_value=("", []))
    def test_macro_baseline_uses_harness_evolution(self, mock_xq, mock_nb, mock_idx, mock_hot, monkeypatch):
        from agent_reach.daily_run.harness import HarnessState, HarnessEntry
        from agent_reach.daily_run.hot_news_collector import HotNewsResult
        from agent_reach.daily_run.macro_collector import collect_macro_context

        state = HarnessState()
        state.entries["memory"]["miss"] = HarnessEntry(
            id="miss",
            kind="memory",
            title="盈亏目标未达",
            content="盈亏目标未达：目标 +100 实际 +0",
            source="deterministic",
            job="close",
            evidence="close",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        monkeypatch.setattr("agent_reach.daily_run.harness.load_harness", lambda: state)
        mock_hot.return_value = HotNewsResult()
        settings = load_settings()
        settings.setdefault("harness", {})["runtime_overlay_sources"] = ["memory"]
        ctx = collect_macro_context({}, settings=settings)
        assert ctx["mss_breakdown"]["_macro_baseline_ref"] == 45.0
        assert ctx["mss_breakdown"]["global"] == 45.0


class TestIntradayMacroRefresh:
    def test_intraday_refresh_macro_mode_default(self):
        from agent_reach.daily_run.macro_collector import intraday_refresh_macro_mode

        assert intraday_refresh_macro_mode({}) == "flow_index"
        assert intraday_refresh_macro_mode({"snapshot": {"intraday_refresh_macro": "off"}}) == "off"
        assert intraday_refresh_macro_mode({"snapshot": {"intraday_refresh_macro": "FULL"}}) == "full"
        assert intraday_refresh_macro_mode({"snapshot": {"intraday_refresh_macro": "bogus"}}) == "flow_index"

    @patch("agent_reach.daily_run.macro_collector._fetch_xueqiu_sentiment", return_value=("雪球热点：存储", []))
    @patch("agent_reach.daily_run.hot_news_collector.collect_hot_news")
    @patch("agent_reach.daily_run.macro_collector._fetch_index_change", return_value=1.0)
    @patch("agent_reach.daily_run.macro_collector._fetch_northbound_flow", return_value=10.0)
    def test_flow_index_scope_skips_sentiment_apis(self, mock_nb, mock_idx, mock_hot, _mock_xq):
        from agent_reach.daily_run.hot_news_collector import HotNewsResult
        from agent_reach.daily_run.macro_collector import collect_macro_context

        mock_hot.return_value = HotNewsResult()
        ctx = collect_macro_context(
            {"mss_breakdown": {"fx": 50, "flow": 50, "global": 50, "sentiment": 62}},
            settings=load_settings(),
            scope="flow_index",
        )
        mock_hot.assert_not_called()
        assert "sentiment" not in ctx["sources"]
        assert ctx["mss_breakdown"]["global"] > 50
        assert ctx["mss_breakdown"]["sentiment"] == 62

    @patch("agent_reach.daily_run.macro_collector._fetch_xueqiu_sentiment", return_value=("", []))
    @patch("agent_reach.daily_run.hot_news_collector.collect_hot_news")
    @patch("agent_reach.daily_run.macro_collector._fetch_index_change", return_value=1.5)
    @patch("agent_reach.daily_run.macro_collector._fetch_northbound_flow", return_value=8.0)
    def test_merge_intraday_macro_context_keeps_cached_sentiment(
        self, mock_nb, mock_idx, mock_hot, _mock_xq
    ):
        from agent_reach.daily_run.hot_news_collector import HotNewsResult
        from agent_reach.daily_run.macro_collector import (
            collect_macro_context,
            merge_intraday_macro_context,
        )

        mock_hot.return_value = HotNewsResult()
        cached = {
            "mss_breakdown": {
                "fx": 47.0,
                "flow": 48.0,
                "global": 46.0,
                "sentiment": 63.0,
            },
            "sources": {
                "sentiment": {"summary": "早盘舆情", "backend": "xueqiu"},
                "hot_news": {"summary": "热榜命中 2", "backend": "60s_api"},
            },
            "macro_summary": "早盘舆情 | 热榜",
            "macro_signals": {"hot_topic_hits": 2, "index_change_pct": -0.5},
        }
        live = collect_macro_context({}, settings=load_settings(), scope="flow_index")
        merged = merge_intraday_macro_context(cached, live, mode="flow_index")
        assert merged["mss_breakdown"]["sentiment"] == 63.0
        assert merged["mss_breakdown"]["global"] == live["mss_breakdown"]["global"]
        assert merged["sources"]["sentiment"]["summary"] == "早盘舆情"
        assert merged["sources"]["flow"]["summary"].startswith("北向")
        assert "大盘 +1.50%" in merged["macro_summary"]
        assert "早盘舆情" in merged["macro_summary"]

    @patch("agent_reach.daily_run.snapshot_builder.resolve_intraday_macro_context")
    @patch("agent_reach.daily_run.snapshot_builder.load_daily_cache")
    @patch("agent_reach.daily_run.snapshot_builder.collect_macro_context")
    @patch("agent_reach.daily_run.snapshot_builder.fetch_quotes_result")
    def test_build_snapshot_intraday_calls_macro_refresh(
        self,
        mock_fetch_result,
        mock_collect,
        mock_cache,
        mock_resolve,
    ):
        from agent_reach.daily_run.quote_fetch import QuoteFetchResult
        from agent_reach.daily_run.snapshot_builder import build_snapshot

        portfolio = {
            "primary_code": "688008",
            "holdings": [{"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87}],
            "watchlist": [{"code": "603986", "name": "兆易创新"}],
        }
        mock_cache.return_value = {
            "macro_ctx": {"mss_breakdown": {"fx": 50, "flow": 50, "global": 50, "sentiment": 60}},
            "technicals": {},
        }
        mock_resolve.return_value = {
            "mss_breakdown": {"fx": 55, "flow": 58, "global": 57, "sentiment": 60},
            "sources": {"flow": {"summary": "北向"}},
            "macro_summary": "live macro",
        }
        mock_fetch_result.return_value = QuoteFetchResult(
            quotes={
                "688008": {"code": "688008", "price": 260.0, "change_pct": 1.0, "source": "xueqiu"},
                "002273": {"code": "002273", "price": 27.0, "change_pct": 0.2, "source": "xueqiu"},
                "603986": {"code": "603986", "price": 450.0, "change_pct": -1.0, "source": "xueqiu"},
            },
            sources_used=["xueqiu"],
        )
        snap = build_snapshot(
            portfolio,
            report_type="intraday",
            settings={"snapshot": {"intraday_enrich_level": "quotes", "intraday_refresh_macro": "flow_index"}},
        )
        mock_resolve.assert_called_once()
        mock_collect.assert_not_called()
        assert snap["mss_breakdown"]["sentiment"] == 60
        assert snap["mss_breakdown"]["flow"] == 58

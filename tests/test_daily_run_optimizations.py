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

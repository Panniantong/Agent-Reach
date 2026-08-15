# -*- coding: utf-8
"""Tests for weekly RedFox diff and market review rollup."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from agent_reach.daily_run.hot_news_collector import HotNewsResult
from agent_reach.daily_run.redfox_collector import RedfoxResult
from agent_reach.daily_run.redfox_weekly import (
    build_hot_topic_diff,
    render_hot_topic_diff_markdown,
    render_market_review_weekly_markdown,
    summarize_week_market_reviews,
)


class TestHotTopicDiff:
    @patch("agent_reach.daily_run.redfox_weekly.collect_redfox_context")
    @patch("agent_reach.daily_run.redfox_weekly.collect_hot_news")
    @patch("agent_reach.daily_run.redfox_weekly.redfox_enabled", return_value=True)
    def test_build_diff_overlap(self, _enabled, mock_hot, mock_rf):
        mock_hot.return_value = HotNewsResult(
            items=[{"title": "芯片板块大涨", "platform": "weibo"}],
        )
        mock_rf.return_value = RedfoxResult(
            trending_items=[{"title": "芯片板块大涨", "platform": "wb"}],
            stock_feed_items=[{"title": "光模块异动", "platform": "xhs"}],
        )
        diff = build_hot_topic_diff(
            {"holdings": [{"name": "澜起科技"}]},
            settings={"hot_news": {"enabled": True}, "redfox": {"weekly_diff": {"enabled": True}}},
        )
        assert diff["overlap_count"] == 1
        assert diff["count_60s"] == 1
        assert diff["count_redfox"] == 2
        md = render_hot_topic_diff_markdown(diff)
        assert "RedFox vs 60s" in md


class TestMarketReviewWeekly:
    @patch("agent_reach.daily_run.redfox_weekly.load_market_review")
    @patch("agent_reach.daily_run.redfox_weekly.is_trading_day", return_value=(True, ""))
    def test_summarize_week(self, _trading, mock_load):
        mock_load.return_value = {
            "sector_analysis": {"mainline_type": "单主线"},
            "emotion": {"rating": "强"},
            "lhb_analysis": {"total_net": 3.5, "summary": {"total_net": 3.5}},
        }
        summary = summarize_week_market_reviews(
            date(2026, 8, 10),
            date(2026, 8, 14),
            settings={"market_review": {"enabled": True}},
        )
        assert summary["days_with_data"] == 5
        assert summary["dominant_mainline"] == "单主线"
        md = render_market_review_weekly_markdown(summary)
        assert "本周全市场复盘汇总" in md

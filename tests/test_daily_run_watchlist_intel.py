# -*- coding: utf-8
"""Tests for watchlist announcement/news intel."""

from unittest.mock import patch

from agent_reach.daily_run.watchlist_intel import (
    classify_intel_sentiment,
    collect_watchlist_intel,
    intel_reason_suffix,
    intel_score_adjustment,
    intel_score_boost,
    render_watchlist_intel_markdown,
    watchlist_intel_narrative_summary,
    watchlist_remove_negative_intel_reason,
)
from agent_reach.daily_run.watchlist_manager import adjust_watchlist


PORTFOLIO = {
    "holdings": [{"code": "688008", "name": "澜起科技"}],
    "watchlist": [{"code": "603986", "name": "兆易创新"}],
}


class TestWatchlistIntel:
    @patch("agent_reach.daily_run.watchlist_intel.fetch_symbol_intel")
    def test_collect_watchlist_intel(self, mock_fetch):
        mock_fetch.return_value = {
            "announcements": [{"title": "业绩预告", "created_at": 1700000000000}],
            "news": [{"title": "机构调研", "created_at": 1700000000000}],
        }
        out = collect_watchlist_intel(PORTFOLIO, settings={})
        assert "603986" in out
        assert out["603986"]["announcements"]

    def test_intel_score_and_reason(self):
        intel = {
            "announcements": [{"title": "重大合同公告"}],
            "news": [{"title": "行业资讯"}],
        }
        boost = intel_score_boost(intel, settings={})
        assert boost >= 4
        assert "公告" in intel_reason_suffix(intel)
        md = render_watchlist_intel_markdown(
            {"603986": {**intel, "name": "兆易创新", "code": "603986"}},
            watchlist=PORTFOLIO["watchlist"],
        )
        assert "观察池公告/资讯" in md

    def test_watchlist_intel_narrative_summary(self):
        summary = watchlist_intel_narrative_summary(
            {
                "watchlist_intel": {
                    "603986": {
                        "name": "兆易创新",
                        "announcements": [{"title": "业绩预告"}],
                        "news": [{"title": "机构调研"}],
                    }
                }
            }
        )
        assert summary.startswith("观察池情报：")
        assert "兆易创新" in summary
        assert "公告" in summary

    def test_negative_intel_penalty_and_removal(self):
        intel = {
            "announcements": [{"title": "收到证监会立案调查通知书"}],
            "sentiment": "negative",
            "headline": "收到证监会立案调查通知书",
        }
        assert classify_intel_sentiment(intel)[0] == "negative"
        assert intel_score_adjustment(intel, settings={}) == -4
        assert "利空" in intel_reason_suffix(intel)
        snapshot = {"watchlist_intel": {"603986": {**intel, "name": "兆易创新", "code": "603986"}}}
        reason = watchlist_remove_negative_intel_reason("603986", snapshot, settings={})
        assert reason and "利空公告" in reason

    def test_negative_news_penalty_only(self):
        intel = {
            "news": [{"title": "行业利空消息扩散"}],
            "sentiment": "negative_news",
        }
        assert classify_intel_sentiment(intel)[0] == "negative_news"
        assert intel_score_adjustment(intel, settings={}) == -2
        snapshot = {"watchlist_intel": {"603986": intel}}
        assert watchlist_remove_negative_intel_reason("603986", snapshot, settings={}) is None

    @patch("agent_reach.daily_run.watchlist_intel.collect_watchlist_intel")
    def test_adjust_watchlist_attaches_intel(self, mock_collect):
        mock_collect.return_value = {
            "603986": {
                "code": "603986",
                "name": "兆易创新",
                "announcements": [{"title": "订单公告"}],
                "news": [],
            }
        }
        snapshot = {
            "mss_final": 55,
            "mss_breakdown": {"fx": 55, "flow": 55, "global": 55, "sentiment": 55},
            "portfolio": PORTFOLIO,
        }
        settings = {
            "watchlist": {
                "auto_adjust_enabled": True,
                "min_size": 0,
                "max_size": 10,
                "hot_topic_adjust_enabled": False,
                "announcement_intel_enabled": True,
            },
            "thresholds": {},
        }
        result = adjust_watchlist(PORTFOLIO, snapshot, settings, "morning")
        assert snapshot.get("watchlist_intel")
        assert mock_collect.called
        assert result.applied or result.message

    @patch("agent_reach.daily_run.watchlist_intel.collect_watchlist_intel")
    def test_adjust_watchlist_removes_negative_intel(self, mock_collect):
        mock_collect.return_value = {
            "603986": {
                "code": "603986",
                "name": "兆易创新",
                "announcements": [{"title": "被证监会立案调查"}],
                "news": [],
                "sentiment": "negative",
                "headline": "被证监会立案调查",
            }
        }
        snapshot = {
            "mss_final": 55,
            "mss_breakdown": {"fx": 55, "flow": 55, "global": 55, "sentiment": 55},
            "portfolio": PORTFOLIO,
        }
        settings = {
            "watchlist": {
                "auto_adjust_enabled": True,
                "min_size": 0,
                "max_size": 10,
                "hot_topic_adjust_enabled": False,
                "announcement_intel_enabled": True,
                "negative_intel_remove_enabled": True,
            },
            "thresholds": {},
        }
        result = adjust_watchlist(PORTFOLIO, snapshot, settings, "morning")
        codes = {w["code"] for w in result.portfolio["watchlist"]}
        assert "603986" not in codes
        assert any("利空公告" in c.reason for c in result.changes if c.action == "remove")

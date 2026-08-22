# -*- coding: utf-8
"""Tests for Xueqiu search_stock integration."""

from unittest.mock import patch

from agent_reach.daily_run.watchlist_candidates import build_weekly_watchlist_candidates
from agent_reach.daily_run.xueqiu_hot_display import render_xueqiu_hot_markdown, xueqiu_hot_context_summary
from agent_reach.daily_run.xueqiu_stock_search import (
    attach_xueqiu_stock_search,
    extract_search_queries,
    is_a_share_symbol,
    search_row_to_match,
)


PORTFOLIO = {
    "holdings": [{"code": "688008", "name": "澜起科技"}],
    "watchlist": [{"code": "603986", "name": "兆易创新"}],
}


class TestXueqiuStockSearch:
    def test_is_a_share_symbol(self):
        assert is_a_share_symbol("SH688008") is True
        assert is_a_share_symbol("AAPL") is False

    def test_search_row_to_match(self):
        row = search_row_to_match(
            {"symbol": "SH688981", "name": "中芯国际", "exchange": "SHA"},
            query="半导体",
            source_title="半导体政策",
        )
        assert row
        assert row["code"] == "688981"
        assert row["query"] == "半导体"

    def test_extract_search_queries(self):
        signals = {
            "hot_topics_matched": [{"title": "半导体景气度回升，存储芯片走强"}],
        }
        queries = extract_search_queries(
            signals,
            PORTFOLIO,
            settings={"hot_news": {"extra_keywords": ["半导体", "存储"]}},
        )
        assert queries
        assert queries[0]["query"] in ("半导体", "存储", "澜起")

    @patch("agent_reach.daily_run.xueqiu_stock_search.search_xueqiu_stocks")
    def test_attach_xueqiu_stock_search(self, mock_search):
        mock_search.return_value = [
            {"symbol": "SH688981", "name": "中芯国际", "exchange": "SHA"},
        ]
        signals = {
            "hot_topics_matched": [{"title": "半导体板块活跃"}],
        }
        out = attach_xueqiu_stock_search(signals, PORTFOLIO, settings={})
        assert len(out["xueqiu_stock_search"]) == 1
        assert out["xueqiu_stock_search"][0]["code"] == "688981"
        md = render_xueqiu_hot_markdown(out)
        assert "热点关键词搜股" in md
        summary = xueqiu_hot_context_summary(out)
        assert "热点搜股" in summary

    @patch("agent_reach.daily_run.xueqiu_stock_search.search_xueqiu_stocks")
    def test_watchlist_candidates_from_search(self, mock_search):
        from agent_reach.daily_run.settings import load_settings

        settings = load_settings()
        settings.setdefault("watchlist", {})
        settings["watchlist"]["weekly_candidates_enabled"] = True
        settings["watchlist"]["weekly_candidates_min"] = 5
        settings["watchlist"]["weekly_candidates_max"] = 10
        settings["watchlist"]["sector_pools"] = {}
        mock_search.return_value = [
            {"symbol": "SH688047", "name": "龙芯中科", "exchange": "SHA"},
        ]
        signals = attach_xueqiu_stock_search(
            {"hot_topics_matched": [{"title": "半导体板块活跃"}]},
            PORTFOLIO,
            settings=settings,
        )
        report = {
            "week_end": "2026-07-25",
            "holdings": PORTFOLIO["holdings"],
            "hot_sectors": [],
            "sector_groups": {},
            "macro_signals": signals,
        }
        update = build_weekly_watchlist_candidates(report, settings)
        codes = {c["code"] for c in update.candidates}
        assert "688047" in codes

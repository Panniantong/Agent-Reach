# -*- coding: utf-8
"""Tests for per-symbol Xueqiu sentiment and overlap-triggered Exa research."""

from unittest.mock import patch

from agent_reach.daily_run.xueqiu_exa_research import (
    attach_xueqiu_exa_research,
    build_xueqiu_overlap_exa_queries,
)
from agent_reach.daily_run.xueqiu_hot_display import (
    render_intraday_xueqiu_alert_markdown,
    render_portfolio_symbol_sentiment_markdown,
    render_xueqiu_exa_research_markdown,
    render_xueqiu_hot_markdown,
    xueqiu_hot_context_summary,
)
from agent_reach.daily_run.xueqiu_symbol_sentiment import attach_portfolio_symbol_sentiment


PORTFOLIO = {
    "holdings": [{"code": "688008", "name": "澜起科技"}],
    "watchlist": [{"code": "603986", "name": "兆易创新"}],
}


class TestPortfolioSymbolSentiment:
    @patch("agent_reach.channels.xueqiu.XueqiuChannel.search_symbol_posts")
    @patch("agent_reach.channels.xueqiu._ensure_cookies")
    def test_attach_portfolio_symbol_sentiment(self, _cookies, mock_posts):
        mock_posts.side_effect = [
            [{"title": "DDR5 景气", "text": "", "author": "分析师", "url": "https://xueqiu.com/1"}],
            [],
        ]
        signals: dict = {}
        out = attach_portfolio_symbol_sentiment(signals, PORTFOLIO, settings={})
        assert len(out["portfolio_symbol_sentiment"]) == 1
        assert out["portfolio_symbol_sentiment"][0]["code"] == "688008"
        md = render_portfolio_symbol_sentiment_markdown(out["portfolio_symbol_sentiment"])
        assert "个股雪球讨论" in md
        assert "DDR5 景气" in md


class TestXueqiuOverlapExa:
    def test_build_queries_from_hot_stock_overlap(self):
        queries = build_xueqiu_overlap_exa_queries(
            {
                "portfolio_hot_stocks": [
                    {
                        "code": "688008",
                        "name": "澜起科技",
                        "role": "holding",
                        "rank": 3,
                        "board": "人气榜",
                    }
                ],
            },
            settings={"macro_collector": {"xueqiu_exa_max_queries": 2}},
        )
        assert len(queries) == 1
        assert "688008" in queries[0]["query"]
        assert "澜起科技" in queries[0]["label"]

    def test_build_queries_from_stock_search(self):
        queries = build_xueqiu_overlap_exa_queries(
            {
                "xueqiu_stock_search": [
                    {
                        "code": "688047",
                        "name": "龙芯中科",
                        "query": "国产CPU",
                    }
                ],
            },
            settings={"macro_collector": {"xueqiu_exa_max_queries": 2}},
        )
        assert len(queries) == 1
        assert queries[0]["type"] == "xueqiu_hot_search"
        assert "688047" in queries[0]["query"]
        assert "国产CPU" in queries[0]["trigger"]

    def test_build_queries_from_new_hot_stock(self):
        queries = build_xueqiu_overlap_exa_queries(
            {
                "portfolio_hot_stocks_new": [
                    {
                        "code": "603986",
                        "name": "兆易创新",
                        "role": "watchlist",
                        "rank": 4,
                        "board": "关注榜",
                    }
                ],
            },
            settings={"macro_collector": {"xueqiu_exa_max_queries": 2}},
        )
        assert len(queries) == 1
        assert queries[0]["type"] == "xueqiu_hot_stock_new"
        assert "603986" in queries[0]["query"]

    @patch("agent_reach.daily_run.xueqiu_exa_research.run_xueqiu_overlap_exa_research")
    def test_attach_xueqiu_exa_research(self, mock_run):
        mock_run.return_value = [
            {
                "label": "澜起科技 · 雪球人气榜",
                "summary": "存储芯片景气延续",
                "success": True,
                "hits": [{"title": "Report", "url": "https://example.com/r"}],
                "trigger": "holding on Xueqiu 人气榜 rank 3",
            }
        ]
        signals = {
            "portfolio_hot_stocks": [{"code": "688008", "name": "澜起科技", "role": "holding"}],
        }
        out = attach_xueqiu_exa_research(signals, settings={})
        assert len(out["xueqiu_exa_research"]) == 1
        md = render_xueqiu_exa_research_markdown(out["xueqiu_exa_research"])
        assert "Exa 调研" in md
        assert "存储芯片景气延续" in md

    def test_render_xueqiu_hot_markdown_includes_symbol_and_exa(self):
        md = render_xueqiu_hot_markdown(
            {
                "portfolio_symbol_sentiment": [
                    {
                        "code": "688008",
                        "name": "澜起科技",
                        "role": "holding",
                        "posts": [{"title": "业绩超预期", "author": "用户A", "url": ""}],
                    }
                ],
                "xueqiu_exa_research": [
                    {
                        "label": "澜起科技 · 雪球人气榜",
                        "summary": "Exa 摘要",
                        "success": True,
                        "hits": [],
                        "trigger": "热股命中",
                    }
                ],
            }
        )
        assert "个股雪球讨论" in md
        assert "业绩超预期" in md
        assert "Exa 调研" in md

    def test_context_summary_prefers_exa_after_overlap(self):
        summary = xueqiu_hot_context_summary(
            {
                "xueqiu_exa_research": [
                    {"label": "澜起", "summary": "景气上行", "success": True},
                ],
            }
        )
        assert summary.startswith("Exa：")


    def test_render_intraday_alert_includes_exa(self):
        md = render_intraday_xueqiu_alert_markdown(
            {
                "portfolio_hot_stocks_new": [
                    {
                        "code": "603986",
                        "name": "兆易创新",
                        "role": "watchlist",
                        "rank": 4,
                        "board": "关注榜",
                    }
                ],
                "xueqiu_exa_research": [
                    {
                        "label": "兆易创新 · 新登关注榜",
                        "summary": "存储景气延续",
                        "success": True,
                    }
                ],
            }
        )
        assert "热股新上榜" in md
        assert "Exa：" in md
        assert "存储景气延续" in md


class TestHotPostMssBoost:
    def test_derive_mss_includes_portfolio_hot_post_boost(self):
        from agent_reach.daily_run.macro_collector import _derive_mss_breakdown

        breakdown = _derive_mss_breakdown(
            {"fx": 50, "flow": 50, "global": 50, "sentiment": 50},
            {"portfolio_hot_posts": [{"title": "a"}, {"title": "b"}]},
            {"macro_collector": {"portfolio_hot_post_boost": 1.5}},
            scope="full",
        )
        assert breakdown["sentiment"] == 53.0


class TestIntradayHotStockDelta:
    def test_apply_intraday_hot_stock_delta_detects_new(self, tmp_path, monkeypatch):
        from agent_reach.daily_run.xueqiu_hot_display import (
            apply_intraday_hot_stock_delta,
            portfolio_hot_stocks_new_summary,
            render_intraday_xueqiu_alert_markdown,
        )

        history = tmp_path / "history.json"
        monkeypatch.setattr(
            "agent_reach.daily_run.xueqiu_hot_display._intraday_hot_stock_history_path",
            lambda: history,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.trade_calendar.today_shanghai",
            lambda: __import__("datetime").date(2026, 7, 25),
        )

        first = {
            "portfolio_hot_stocks": [
                {
                    "code": "688008",
                    "name": "澜起科技",
                    "role": "holding",
                    "rank": 3,
                    "board": "人气榜",
                    "percent": 1.2,
                }
            ]
        }
        out1 = apply_intraday_hot_stock_delta(dict(first), settings={})
        assert out1.get("portfolio_hot_stocks_new")
        assert "新登" in portfolio_hot_stocks_new_summary(out1)

        second = apply_intraday_hot_stock_delta(dict(first), settings={})
        assert not second.get("portfolio_hot_stocks_new")

        third_signals = {
            "portfolio_hot_stocks": first["portfolio_hot_stocks"]
            + [
                {
                    "code": "603986",
                    "name": "兆易创新",
                    "role": "watchlist",
                    "rank": 8,
                    "board": "关注榜",
                    "percent": -0.4,
                }
            ]
        }
        out3 = apply_intraday_hot_stock_delta(dict(third_signals), settings={})
        assert len(out3["portfolio_hot_stocks_new"]) == 1
        assert out3["portfolio_hot_stocks_new"][0]["code"] == "603986"

        md = render_intraday_xueqiu_alert_markdown(out1)
        assert "热股新上榜" in md

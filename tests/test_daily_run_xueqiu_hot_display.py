# -*- coding: utf-8
"""Tests for Xueqiu hot display in morning push."""

from unittest.mock import patch

from agent_reach.daily_run.report_push import (
    append_merged_xueqiu_hot_section,
    render_morning_sections,
)
from agent_reach.daily_run.xueqiu_hot_display import (
    apply_portfolio_hot_post_matches,
    apply_portfolio_hot_stock_matches,
    enrich_portfolio_xueqiu_matches,
    match_portfolio_hot_posts,
    match_portfolio_hot_stocks,
    portfolio_hot_post_summary,
    portfolio_hot_stock_summary,
    render_xueqiu_hot_markdown,
    sync_xueqiu_sentiment_source,
    xueqiu_hot_context_summary,
    xueqiu_sentiment_source_summary,
)


PORTFOLIO = {
    "holdings": [{"code": "688008", "name": "澜起科技"}],
    "watchlist": [{"code": "603986", "name": "兆易创新"}],
}


class TestPortfolioHotPostOverlap:
    def test_match_portfolio_hot_posts_by_keyword(self):
        posts = [
            {"title": "澜起科技业绩超预期", "author": "分析师", "likes": 12},
            {"title": "宏观周报", "author": "路人", "likes": 1},
        ]
        matches = match_portfolio_hot_posts(PORTFOLIO, posts, settings={})
        assert len(matches) == 1
        assert any("澜起" in kw for kw in matches[0]["matched_keywords"])

    def test_apply_and_render_portfolio_hot_posts(self):
        signals = {
            "sentiment_posts": [
                {"title": "兆易创新存储逻辑", "author": "雪球用户", "url": "https://xueqiu.com/1"},
            ],
        }
        out = apply_portfolio_hot_post_matches(dict(signals), PORTFOLIO, settings={})
        assert len(out["portfolio_hot_posts"]) == 1
        summary = portfolio_hot_post_summary(out)
        assert summary.startswith("热帖命中：")
        md = render_xueqiu_hot_markdown(out)
        assert "持仓相关热帖" in md
        assert "兆易创新" in md

    def test_enrich_portfolio_xueqiu_matches(self):
        signals = {
            "sentiment_posts": [{"title": "澜起科技点评", "author": "x"}],
            "hot_stocks": [{"rank": 1, "name": "澜起科技", "symbol": "688008", "percent": 1.0}],
        }
        out = enrich_portfolio_xueqiu_matches(dict(signals), PORTFOLIO, settings={})
        assert out.get("portfolio_hot_stocks")
        assert out.get("portfolio_hot_posts")

    def test_xueqiu_hot_context_summary_prefers_post_overlap(self):
        summary = xueqiu_hot_context_summary(
            {
                "portfolio_hot_posts": [
                    {"title": "澜起科技深度", "matched_keywords": ["澜起"]},
                ],
                "sentiment_posts": [{"title": "其它热帖"}],
            }
        )
        assert summary.startswith("热帖命中：")


class TestPortfolioHotStockOverlap:
    def test_match_portfolio_hot_stocks_holding_and_watchlist(self):
        hot = [
            {"rank": 3, "name": "澜起科技", "symbol": "SH688008", "percent": 1.2, "board": "人气榜", "board_type": 10},
            {"rank": 7, "name": "兆易创新", "symbol": "SH603986", "percent": -0.5, "board": "关注榜", "board_type": 12},
            {"rank": 1, "name": "其它", "symbol": "SH600000", "percent": 2.0, "board": "人气榜", "board_type": 10},
        ]
        matches = match_portfolio_hot_stocks(PORTFOLIO, hot)
        assert len(matches) == 2
        assert matches[0]["code"] == "688008"
        assert matches[0]["role"] == "holding"
        assert matches[0]["rank"] == 3
        assert matches[1]["code"] == "603986"
        assert matches[1]["role"] == "watchlist"

    def test_apply_portfolio_hot_stock_matches(self):
        signals = {
            "hot_stocks": [{"rank": 2, "name": "澜起科技", "symbol": "688008", "percent": 0.8}],
            "hot_watch_stocks": [{"rank": 5, "name": "兆易创新", "symbol": "SZ603986", "percent": -1.1}],
        }
        out = apply_portfolio_hot_stock_matches(dict(signals), PORTFOLIO, settings={})
        assert len(out["portfolio_hot_stocks"]) == 2
        summary = portfolio_hot_stock_summary(out)
        assert summary.startswith("热股命中：")
        assert "澜起科技" in summary
        assert "兆易创新" in summary

    def test_render_overlap_section(self):
        macro_signals = {
            "portfolio_hot_stocks": [
                {
                    "code": "688008",
                    "name": "澜起科技",
                    "role": "holding",
                    "rank": 3,
                    "board": "人气榜",
                    "percent": 1.25,
                    "current": 199.1,
                }
            ],
            "hot_stocks": [{"rank": 1, "name": "其它", "symbol": "SH600000", "percent": 2.0}],
        }
        md = render_xueqiu_hot_markdown(macro_signals)
        assert "持仓/观察池 × 雪球热股" in md
        assert "澜起科技" in md
        assert "人气榜 #3" in md


class TestXueqiuHotDisplay:
    def test_render_xueqiu_hot_markdown_posts_and_stocks(self):
        macro_signals = {
            "sentiment_posts": [
                {
                    "title": "存储芯片景气",
                    "author": "张三",
                    "likes": 88,
                    "url": "https://xueqiu.com/u/1/123",
                }
            ],
            "hot_stocks": [
                {
                    "rank": 1,
                    "name": "澜起科技",
                    "symbol": "SH688008",
                    "current": 199.1,
                    "percent": 1.25,
                }
            ],
        }
        md = render_xueqiu_hot_markdown(macro_signals)
        assert "雪球热门" in md
        assert "热帖 Top1" in md
        assert "存储芯片景气" in md
        assert "张三" in md
        assert "https://xueqiu.com/u/1/123" in md
        assert "热股 Top1" in md
        assert "澜起科技" in md
        assert "+1.25%" in md

    def test_render_xueqiu_hot_markdown_empty(self):
        assert render_xueqiu_hot_markdown(None) == ""
        assert render_xueqiu_hot_markdown({}) == ""

    def test_sync_xueqiu_sentiment_source_overrides_portfolio(self):
        sources = {
            "sentiment": {"summary": "雪球存储芯片/DDR5 景气讨论活跃"},
            "flow": {"summary": "北向净流入"},
        }
        macro_signals = {
            "sentiment_posts": [{"title": "读懂腾讯财报", "text": ""}],
        }
        out = sync_xueqiu_sentiment_source(sources, macro_signals)
        assert out["sentiment"]["backend"] == "xueqiu"
        assert "读懂腾讯财报" in out["sentiment"]["summary"]
        assert out["flow"]["summary"] == "北向净流入"

    def test_xueqiu_hot_context_summary_prefers_overlap(self):
        summary = xueqiu_hot_context_summary(
            {
                "portfolio_hot_stocks": [
                    {"name": "澜起科技", "role": "holding", "rank": 3, "board": "人气榜", "percent": 1.2}
                ],
                "sentiment_posts": [{"title": "其它热帖"}],
            }
        )
        assert summary.startswith("热股命中：")
        assert "澜起科技" in summary

    def test_xueqiu_hot_context_summary(self):
        summary = xueqiu_hot_context_summary(
            {
                "sentiment_posts": [{"title": "存储芯片"}],
                "hot_stocks": [{"name": "澜起科技", "percent": 1.2}],
            }
        )
        assert "存储芯片" in summary
        assert "澜起科技+1.2%" in summary

    def test_xueqiu_sentiment_source_summary(self):
        summary = xueqiu_sentiment_source_summary(
            [{"title": "A"}, {"title": "B"}, {"title": "C"}],
            max_titles=2,
        )
        assert summary == "雪球热点：A | B"


class TestMorningXueqiuPush:
    def test_render_morning_sections_includes_xueqiu_hot(self):
        sections = render_morning_sections(
            team_markdown="",
            report_markdown="**Decision**",
            report={"name": "澜起", "verdict": "可做"},
            macro_signals={
                "sentiment_posts": [{"title": "热帖1", "author": "作者"}],
                "hot_stocks": [{"rank": 1, "name": "热股", "symbol": "SH600000", "percent": 2.0}],
            },
        )
        cats = [s.category for s in sections]
        assert "decision" in cats
        assert "xueqiu_hot" in cats
        hot = next(s for s in sections if s.category == "xueqiu_hot")
        assert "热帖1" in hot.body
        assert "热股" in hot.body

    def test_append_merged_xueqiu_hot_section(self):
        from agent_reach.daily_run.report_push import ReportSection

        sections = [
            ReportSection(category="decision", title="t1", body="decision body"),
        ]
        out = append_merged_xueqiu_hot_section(
            sections,
            {"sentiment_posts": [{"title": "合并热帖", "author": "x"}]},
            report_kind="morning",
            symbol_count=3,
        )
        assert len(out) == 2
        assert out[0].category == "decision"
        assert out[1].category == "xueqiu_hot"
        assert "合并热帖" in out[1].body
        assert "3只" in out[1].title


class TestCloseXueqiuPush:
    def test_render_close_sections_includes_xueqiu_hot(self):
        from agent_reach.daily_run.report_push import render_close_sections

        sections = render_close_sections(
            verify_name="澜起",
            verify_markdown="**验证**",
            macro_signals={
                "sentiment_posts": [{"title": "收盘热帖", "author": "作者"}],
            },
        )
        cats = [s.category for s in sections]
        assert "verify" in cats
        assert "xueqiu_hot" in cats
        hot = next(s for s in sections if s.category == "xueqiu_hot")
        assert "收盘热帖" in hot.body


class TestIntradayXueqiuAlert:
    def test_render_intraday_xueqiu_alert_markdown(self):
        from agent_reach.daily_run.xueqiu_hot_display import render_intraday_xueqiu_alert_markdown

        md = render_intraday_xueqiu_alert_markdown(
            {
                "portfolio_hot_stocks": [
                    {
                        "name": "澜起科技",
                        "role": "holding",
                        "rank": 2,
                        "board": "人气榜",
                        "percent": 1.5,
                    }
                ],
            }
        )
        assert "雪球交叉提醒" in md
        assert "热股命中" in md
        assert "澜起科技" in md

    def test_fetch_xueqiu_hot_stocks_accepts_stock_type(self):
        from agent_reach.daily_run.macro_collector import _fetch_xueqiu_hot_stocks

        with patch("agent_reach.channels.xueqiu.XueqiuChannel") as mock_cls:
            mock_cls.return_value.get_hot_stocks.return_value = [
                {"symbol": "SH688981", "name": "中芯国际", "percent": 1.0},
            ]
            watch = _fetch_xueqiu_hot_stocks(limit=5, stock_type=12)
        mock_cls.return_value.get_hot_stocks.assert_called_once_with(limit=5, stock_type=12)
        assert watch[0]["board"] == "关注榜"
        assert watch[0]["board_type"] == 12

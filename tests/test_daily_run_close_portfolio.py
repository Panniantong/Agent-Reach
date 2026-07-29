# -*- coding: utf-8
"""Tests for close review portfolio / P&L summary."""

from agent_reach.daily_run.close_portfolio_summary import (
    build_close_portfolio_summary,
    render_close_portfolio_markdown,
)
from agent_reach.daily_run.report_push import merge_sections_by_category, render_close_sections


def _morning_baseline():
    return {
        "code": "688008",
        "name": "澜起科技",
        "price": 250.0,
        "portfolio": {
            "total": 100000.0,
            "cash": 48673.0,
            "cash_ratio": 0.4867,
            "holdings": [
                {"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87, "price": 250.0},
                {"code": "002273", "name": "水晶光电", "shares": 300, "cost": 33.81, "price": 34.0},
                {"code": "002583", "name": "海能达", "shares": 1000, "cost": 19.38, "price": 19.0},
            ],
        },
        "watchlist": [
            {"code": "603986", "name": "兆易创新", "price": 120.0, "change_pct": 1.5},
            {"code": "000725", "name": "京东方A", "price": 4.2, "change_pct": -0.5},
        ],
    }


def _close_snapshot():
    return {
        "code": "688008",
        "name": "澜起科技",
        "price": 260.0,
        "change_pct": 4.0,
        "portfolio": {
            "total": 101500.0,
            "cash": 48673.0,
            "cash_ratio": 0.4795,
            "holdings": [
                {"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87, "price": 260.0, "change_pct": 4.0},
                {"code": "002273", "name": "水晶光电", "shares": 300, "cost": 33.81, "price": 35.0, "change_pct": 2.9},
                {"code": "002583", "name": "海能达", "shares": 1000, "cost": 19.38, "price": 18.5, "change_pct": -2.6},
            ],
        },
        "watchlist": [
            {"code": "603986", "name": "兆易创新", "price": 122.0, "change_pct": 1.7},
            {"code": "000725", "name": "京东方A", "price": 4.1, "change_pct": -2.4},
        ],
    }


class TestClosePortfolioSummary:
    def test_build_daily_pnl(self):
        summary = build_close_portfolio_summary(_close_snapshot(), _morning_baseline())
        assert summary.start_total == 100000.0
        assert summary.end_total == 103673.0
        assert summary.daily_pnl == 3673.0
        assert summary.daily_pnl_pct == 3.67
        assert summary.holdings_count == 3
        assert summary.cash == 48673.0
        assert summary.winners >= 1
        assert summary.reason_lines

    def test_render_markdown_is_portfolio_level(self):
        summary = build_close_portfolio_summary(_close_snapshot(), _morning_baseline())
        md = render_close_portfolio_markdown(summary)
        assert "## 💰 当日盈亏" in md
        assert "组合" in md or "¥" in md
        assert "## 📊 持仓与现金" in md
        assert "持仓 **3** 只" in md
        assert "## 📝 原因摘要" in md
        assert "澜起科技" not in md
        assert "688008" not in md

    def test_render_close_sections_includes_portfolio_last(self):
        md = render_close_portfolio_markdown(
            build_close_portfolio_summary(_close_snapshot(), _morning_baseline())
        )
        sections = render_close_sections(
            verify_name="澜起科技",
            verify_markdown="验证摘要",
            portfolio_markdown=md,
        )
        assert sections[-1].category == "daily_portfolio"
        assert "原因摘要" in sections[-1].body

    def test_merge_skips_per_symbol_portfolio(self):
        from agent_reach.daily_run.report_push import ReportSection

        md_a = render_close_portfolio_markdown(
            build_close_portfolio_summary(_close_snapshot(), _morning_baseline())
        )
        groups = [
            (
                "澜起科技",
                [
                    ReportSection(category="verify", title="", body="验证A"),
                    ReportSection(category="daily_portfolio", title="", body=md_a),
                ],
            ),
            (
                "水晶光电",
                [
                    ReportSection(category="verify", title="", body="验证B"),
                    ReportSection(category="daily_portfolio", title="", body="不应出现"),
                ],
            ),
        ]
        merged = merge_sections_by_category(groups, report_kind="close")
        cats = [s.category for s in merged]
        assert "daily_portfolio" not in cats
        assert any("验证A" in s.body for s in merged)

    def test_missing_baseline_note(self):
        baseline = {"code": "688008", "portfolio": {}}
        summary = build_close_portfolio_summary(_close_snapshot(), baseline)
        assert summary.daily_pnl is None
        md = render_close_portfolio_markdown(summary)
        assert "缺少早盘净值基线" in md or "收盘净值" in md

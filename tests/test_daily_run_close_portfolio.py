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
        assert summary.holdings_count == 3
        assert summary.reason_lines

    def test_render_includes_stocks_trades_watchlist(self):
        summary = build_close_portfolio_summary(
            _close_snapshot(),
            _morning_baseline(),
            watchlist_adjust={
                "applied": True,
                "changes": [
                    {
                        "action": "add",
                        "code": "000725",
                        "name": "京东方A",
                        "reason": "补足观察池下限（热点优先）",
                    }
                ],
            },
            intraday_trades=[
                {
                    "action": "hold",
                    "name": "澜起科技",
                    "code": "688008",
                }
            ],
        )
        md = render_close_portfolio_markdown(summary)
        assert "## 💰 组合盈亏" in md
        assert "## 📈 个股盈亏" in md
        assert "澜起科技" in md
        assert "水晶光电" in md
        assert "## 🔄 成交记录" in md
        assert "## 👀 观察池" in md
        assert "补足观察池下限" in md
        assert "京东方A" in md
        assert "## 📝 原因摘要" in md

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
        assert "个股盈亏" in sections[-1].body

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
        ]
        merged = merge_sections_by_category(groups, report_kind="close")
        assert "daily_portfolio" not in [s.category for s in merged]

    def test_missing_baseline_skips_false_position_change(self):
        baseline = {"code": "688008", "portfolio": {}}
        summary = build_close_portfolio_summary(_close_snapshot(), baseline)
        assert summary.daily_pnl is None
        assert "基线无持仓快照" in summary.position_change

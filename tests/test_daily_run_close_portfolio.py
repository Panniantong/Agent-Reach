# -*- coding: utf-8
"""Tests for close review portfolio / P&L summary."""

from agent_reach.daily_run.close_portfolio_summary import (
    build_close_portfolio_summary,
    render_close_portfolio_markdown,
)
from agent_reach.daily_run.report_push import render_close_sections


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
        assert len(summary.holdings) == 3
        assert summary.cash == 48673.0

    def test_render_markdown_sections(self):
        summary = build_close_portfolio_summary(_close_snapshot(), _morning_baseline())
        md = render_close_portfolio_markdown(summary)
        assert "## 💰 当日盈亏" in md
        assert "组合净值变动" in md
        assert "## 📊 持仓分布" in md
        assert "权重" in md
        assert "## 💵 现金" in md
        assert "## 📝 盈亏归因" in md
        assert "澜起科技" in md

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
        assert "当日盈亏" in sections[-1].body

    def test_missing_baseline_note(self):
        baseline = {"code": "688008", "portfolio": {}}
        summary = build_close_portfolio_summary(_close_snapshot(), baseline)
        assert summary.daily_pnl is None
        md = render_close_portfolio_markdown(summary)
        assert "缺少早盘净值基线" in md or "暂无完整净值" in md

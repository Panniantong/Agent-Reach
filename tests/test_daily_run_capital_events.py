# -*- coding: utf-8
"""Tests for capital event tracking and P&L adjustment."""

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_reach.daily_run.capital_events import (
    append_capital_event,
    load_capital_events,
    net_capital_flow,
)
from agent_reach.daily_run.close_portfolio_summary import build_close_portfolio_summary
from agent_reach.daily_run.quote_fetch import QuoteFetchResult
from tests.test_daily_run_close_portfolio import _close_snapshot, _morning_baseline


def _build_summary_no_quotes(*args, **kwargs):
    with patch(
        "agent_reach.daily_run.quote_fetch.fetch_quotes_map",
        return_value=QuoteFetchResult(),
    ):
        return build_close_portfolio_summary(*args, **kwargs)


class TestCapitalEvents:
    def test_append_and_load(self, tmp_path: Path):
        path = tmp_path / "capital_events.jsonl"
        day = date(2026, 8, 17)
        append_capital_event("deposit", 100000, note="追加本金", event_date=day, path=path)
        append_capital_event("withdraw", 20000, note="取出", event_date=day, path=path)

        events = load_capital_events(path=path)
        assert len(events) == 2
        assert events[0].kind == "deposit"
        assert events[0].amount == 100000.0
        assert net_capital_flow(day, path=path) == 80000.0

    def test_invalid_kind_or_amount(self, tmp_path: Path):
        path = tmp_path / "capital_events.jsonl"
        with pytest.raises(ValueError, match="kind"):
            append_capital_event("transfer", 100, path=path)
        with pytest.raises(ValueError, match="amount"):
            append_capital_event("deposit", -1, path=path)

    def test_daily_pnl_excludes_deposit(self):
        day = date(2026, 8, 17)
        morning = _morning_baseline()
        close = _close_snapshot()
        close["portfolio"] = dict(close["portfolio"])
        close["portfolio"]["cash"] = float(close["portfolio"]["cash"]) + 100000
        close["portfolio"]["total"] = float(close["portfolio"]["total"]) + 100000

        with patch(
            "agent_reach.daily_run.capital_events.net_capital_flow",
            return_value=100000.0,
        ):
            summary = _build_summary_no_quotes(close, morning, as_of=day)

        assert summary.cash_delta == 100000.0
        assert summary.capital_net_flow == 100000.0
        assert summary.day_mv_change == 800.0
        # NAV change 800; deposit excluded from P&L
        assert summary.daily_pnl == 800.0
        assert summary.end_total == pytest.approx(summary.start_total + 100800.0, abs=0.02)

    def test_daily_pnl_with_deposit_and_cash_spend(self):
        """Simulates deposit + buy: cash_delta mixes flows; PnL excludes deposit only."""
        day = date(2026, 8, 17)
        morning = {
            "portfolio": {
                "cash": 48673.0,
                "holdings": [
                    {"code": "688008", "name": "澜起", "shares": 100, "cost": 255.0, "price": 250.0},
                ],
            }
        }
        close = {
            "portfolio": {
                "cash": 75439.31,
                "holdings": [
                    {"code": "688008", "name": "澜起", "shares": 100, "cost": 255.0, "price": 255.87, "change_pct": 2.35},
                    {"code": "600584", "name": "长电", "shares": 800, "cost": 80.8, "price": 80.8, "change_pct": 0.0},
                ],
            }
        }

        with patch(
            "agent_reach.daily_run.capital_events.net_capital_flow",
            return_value=100000.0,
        ):
            summary = _build_summary_no_quotes(close, morning, as_of=day)

        assert summary.cash_delta == pytest.approx(75439.31 - 48673.0, abs=0.01)
        assert summary.daily_pnl is not None
        assert summary.start_total is not None and summary.end_total is not None
        assert summary.daily_pnl == pytest.approx(
            float(summary.end_total) - float(summary.start_total) - 100000.0,
            abs=0.02,
        )
        assert summary.daily_pnl < 5000

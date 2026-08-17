# -*- coding: utf-8
"""Tests for MSS-driven paper portfolio auto-adjust."""

import pytest

from agent_reach.daily_run.intraday import TradeDecision
from agent_reach.daily_run.portfolio_manager import (
    apply_auto_adjust,
    increment_holding_days,
    is_auto_adjust_enabled,
    max_holdings,
    max_total_symbols,
    unique_symbol_count,
    watchlist_capacity,
)
from agent_reach.daily_run.settings import load_settings


@pytest.fixture
def portfolio():
    return {
        "total": 100000,
        "cash": 61000,
        "cash_ratio": 0.61,
        "holdings": [
            {"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87, "days_held": 5},
            {"code": "002273", "name": "水晶光电", "shares": 300, "cost": 33.81, "days_held": 5},
        ],
        "watchlist": [
            {"code": "603986", "name": "兆易创新"},
            {"code": "000725", "name": "京东方A"},
        ],
    }


@pytest.fixture
def snapshot(portfolio):
    holdings = [
        {**h, "price": 247.15 if h["code"] == "688008" else 32.04, "change_pct": -2.39 if h["code"] == "688008" else -6.23}
        for h in portfolio["holdings"]
    ]
    watchlist = [
        {"code": "603986", "name": "兆易创新", "price": 603.17, "change_pct": -2.71},
        {"code": "000725", "name": "京东方A", "price": 7.63, "change_pct": 0.66},
    ]
    return {
        "code": "688008",
        "price": 247.15,
        "portfolio": {"total": 100000, "cash": 61000, "cash_ratio": 0.61, "holdings": holdings},
        "watchlist": watchlist,
    }


@pytest.fixture
def settings_enabled():
    s = load_settings()
    s.setdefault("portfolio", {})
    s["portfolio"]["auto_adjust_enabled"] = True
    s["portfolio"]["max_holdings"] = 10
    return s


class TestPortfolioConfig:
    def test_defaults(self):
        from agent_reach.daily_run.settings import _DEFAULT_PATH

        s = load_settings(_DEFAULT_PATH)
        assert max_holdings(s) == 10
        assert max_total_symbols(s) == 15
        assert is_auto_adjust_enabled(s) is True

    def test_unique_symbol_count(self, portfolio):
        from agent_reach.daily_run.settings import _DEFAULT_PATH

        assert unique_symbol_count(portfolio) == 4
        assert watchlist_capacity(load_settings(_DEFAULT_PATH), portfolio) == 13


class TestApplyAutoAdjust:
    def test_hold_skips(self, portfolio, snapshot, settings_enabled):
        decision = TradeDecision(
            action="hold",
            trade_id="T1",
            lookback_mss=48.0,
            lookback_detail=[],
            trend="flat",
            reasoning="观望",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_enabled)
        assert result.applied is False
        assert len(result.actions) == 0

    def test_sell_weakest(self, portfolio, snapshot, settings_enabled):
        decision = TradeDecision(
            action="sell",
            trade_id="T1",
            lookback_mss=35.0,
            lookback_detail=[],
            trend="falling",
            reasoning="宏观避险",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_enabled)
        assert result.applied is True
        assert result.actions[0].side == "sell"
        # 水晶光电 change_pct -6.23 worse than 澜起 -2.39
        assert result.actions[0].code == "002273"
        codes = {h["code"] for h in result.portfolio["holdings"]}
        assert "002273" not in codes
        assert result.portfolio["cash"] > portfolio["cash"]
        watch_codes = {w["code"] for w in result.portfolio["watchlist"]}
        assert "002273" not in watch_codes

    def test_sell_adds_watchlist_when_allowed(self, portfolio, snapshot, settings_enabled):
        decision = TradeDecision(
            action="sell",
            trade_id="T1",
            lookback_mss=35.0,
            lookback_detail=[],
            trend="falling",
            reasoning="宏观避险",
        )
        portfolio["holdings"][0]["days_held"] = 5
        portfolio["holdings"][1]["days_held"] = 5
        result = apply_auto_adjust(
            portfolio,
            decision,
            snapshot,
            settings_enabled,
            allow_watchlist_changes=True,
        )
        assert result.applied is True
        watch_codes = {w["code"] for w in result.portfolio["watchlist"]}
        assert "002273" in watch_codes

    def test_sell_respects_lock(self, portfolio, snapshot, settings_enabled):
        portfolio["holdings"][0]["days_held"] = 0
        portfolio["holdings"][0].pop("acquired_date", None)
        portfolio["holdings"][1]["days_held"] = 0
        portfolio["holdings"][1].pop("acquired_date", None)
        decision = TradeDecision(
            action="sell",
            trade_id="T1",
            lookback_mss=35.0,
            lookback_detail=[],
            trend="falling",
            reasoning="宏观避险",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_enabled)
        assert result.applied is False

    def test_buy_from_watchlist(self, portfolio, snapshot, settings_enabled):
        decision = TradeDecision(
            action="buy",
            trade_id="T1",
            lookback_mss=55.0,
            lookback_detail=[],
            trend="rising",
            reasoning="MSS 达阈值",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_enabled)
        assert result.applied is True
        assert result.actions[0].side == "buy"
        assert result.actions[0].code in ("603986", "000725")
        assert len(result.portfolio["holdings"]) == 3
        assert result.portfolio["cash"] < portfolio["cash"]

    def test_max_total_blocks_buy_when_full(self, portfolio, snapshot, settings_enabled):
        settings_enabled["portfolio"]["max_holdings"] = 4
        portfolio["holdings"] = [
            {"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87, "days_held": 5},
            {"code": "002273", "name": "水晶光电", "shares": 300, "cost": 33.81, "days_held": 5},
            {"code": "603986", "name": "兆易创新", "shares": 100, "cost": 600.0, "days_held": 5},
            {"code": "000725", "name": "京东方A", "shares": 1000, "cost": 7.5, "days_held": 5},
        ]
        portfolio["watchlist"] = []
        decision = TradeDecision(
            action="buy",
            trade_id="T1",
            lookback_mss=55.0,
            lookback_detail=[],
            trend="rising",
            reasoning="买",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_enabled)
        assert result.applied is False
        assert "合计上限" in result.message or "观察池" in result.message

    def test_buy_blocked_by_friction(self, portfolio, snapshot, settings_enabled):
        decision = TradeDecision(
            action="buy",
            trade_id="T1",
            lookback_mss=55.0,
            lookback_detail=[],
            trend="rising",
            reasoning="买",
            friction_blocked=True,
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_enabled)
        assert result.applied is False

    def test_disabled(self, portfolio, snapshot):
        s = load_settings()
        s["portfolio"] = {"auto_adjust_enabled": False}
        decision = TradeDecision(
            action="buy",
            trade_id="T1",
            lookback_mss=55.0,
            lookback_detail=[],
            trend="rising",
            reasoning="买",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, s)
        assert result.applied is False


class TestIncrementDays:
    def test_sync_without_acquired_date_keeps_counter(self, portfolio):
        updated = increment_holding_days(portfolio)
        assert updated["holdings"][0]["days_held"] == 5

    def test_sync_from_acquired_date_t_plus_one(self):
        from datetime import date
        from unittest.mock import patch

        from agent_reach.daily_run.portfolio_manager import holding_is_sellable, sync_portfolio_holding_days

        pf = {"holdings": [{"code": "000725", "acquired_date": "2026-07-24", "days_held": 0}]}
        with patch("agent_reach.daily_run.trade_calendar.today_shanghai", return_value=date(2026, 7, 24)):
            assert holding_is_sellable(pf["holdings"][0], {"trading": {"holding_lock_days": 1}}) is False
        with patch("agent_reach.daily_run.trade_calendar.today_shanghai", return_value=date(2026, 7, 27)):
            synced = sync_portfolio_holding_days(pf)
            assert synced["holdings"][0]["days_held"] == 1
            assert holding_is_sellable(synced["holdings"][0], {"trading": {"holding_lock_days": 1}}) is True

    def test_load_portfolio_syncs_days_held(self):
        from datetime import date
        from unittest.mock import patch

        from agent_reach.daily_run.snapshot_builder import load_portfolio

        raw = {
            "holdings": [{"code": "000725", "acquired_date": "2026-07-24", "days_held": 0}],
            "watchlist": [{"code": "603986"}],
        }
        with patch(
            "agent_reach.daily_run.snapshot_builder.json.loads",
            return_value=raw,
        ), patch(
            "agent_reach.daily_run.snapshot_builder.default_portfolio_path",
        ) as mock_path, patch(
            "agent_reach.daily_run.trade_calendar.today_shanghai",
            return_value=date(2026, 7, 27),
        ), patch(
            "agent_reach.daily_run.settings.load_settings",
            return_value={"trading": {"holding_lock_days": 1}, "thresholds": {"max_snapshot_age_hours": 24}},
        ):
            mock_path.return_value.exists.return_value = True
            loaded = load_portfolio()
        assert loaded["holdings"][0]["days_held"] == 1


class TestTradeLedgerDedup:
    def test_dedupe_trade_ledger_entries(self):
        from agent_reach.daily_run.portfolio_manager import dedupe_trade_ledger_entries

        entries = [
            {
                "at": "2026-07-29T13:44:18+00:00",
                "actions": [
                    {
                        "side": "buy",
                        "code": "000725",
                        "shares": 5300,
                        "price": 7.5,
                        "amount": 39750.0,
                    }
                ],
            },
            {
                "at": "2026-07-29T14:10:24+00:00",
                "actions": [
                    {
                        "side": "buy",
                        "code": "000725",
                        "shares": 5300,
                        "price": 7.5,
                        "amount": 39750.0,
                    }
                ],
            },
        ]
        assert len(dedupe_trade_ledger_entries(entries)) == 1

    def test_register_applied_trade_blocks_duplicate(self, tmp_path, monkeypatch):
        from agent_reach.daily_run.portfolio_manager import (
            TradeAction,
            load_daily_trade_state,
            register_applied_trade,
        )

        state_path = tmp_path / "daily_trade_state.json"
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager.daily_trade_state_path",
            lambda: state_path,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager._today_str",
            lambda: "2026-07-31",
        )
        action = TradeAction(
            side="buy",
            code="000725",
            name="京东方A",
            shares=5300,
            price=7.5,
            amount=39750.0,
            commission=59.62,
            reasoning="test",
        )
        assert register_applied_trade([action]) is True
        assert register_applied_trade([action]) is False
        assert len(load_daily_trade_state()["fingerprints"]) == 1

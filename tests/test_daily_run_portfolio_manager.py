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
def settings_enabled(monkeypatch):
    s = load_settings()
    s.setdefault("portfolio", {})
    s["portfolio"]["auto_adjust_enabled"] = True
    s["portfolio"]["max_holdings"] = 10
    s.setdefault("harness_runtime", {})
    s["harness_runtime"]["position_policy"] = {
        "deploy_ratio": 1.0,
        "max_position_pct": 100.0,
    }
    monkeypatch.setattr(
        "agent_reach.daily_run.portfolio_manager.effective_settings",
        lambda settings=None: settings if settings is not None else s,
    )
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

    def test_sell_decision_symbol_only(self, portfolio, snapshot, settings_enabled, monkeypatch):
        settings_enabled["harness_runtime"] = {
            "deep_loss_policy": {
                "loss_cny_threshold": 5000,
                "loss_pct_threshold": 10,
                "cover_ratio": 0.0,
                "sell_ratio": 1.0,
                "non_deep_loss_sell_ratio": 1.0,
            }
        }
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager.effective_settings",
            lambda s: s,
        )
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
        # snapshot.code=688008：只卖澜起，不卖 change_pct 更弱的水晶光电
        assert result.actions[0].code == "688008"
        codes = {h["code"] for h in result.portfolio["holdings"]}
        assert "688008" not in codes
        assert "002273" in codes
        assert result.portfolio["cash"] > portfolio["cash"]
        watch_codes = {w["code"] for w in result.portfolio["watchlist"]}
        assert "688008" not in watch_codes

    def test_sell_skips_when_decision_symbol_not_held(self, portfolio, snapshot, settings_enabled):
        snapshot = dict(snapshot)
        snapshot["code"] = "603986"
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
        assert "不在持仓中" in result.message
        assert len(result.portfolio["holdings"]) == 2

    def test_sell_adds_watchlist_when_allowed(self, portfolio, snapshot, settings_enabled, monkeypatch):
        settings_enabled["harness_runtime"] = {
            "deep_loss_policy": {
                "loss_cny_threshold": 5000,
                "loss_pct_threshold": 10,
                "cover_ratio": 0.0,
                "sell_ratio": 1.0,
                "non_deep_loss_sell_ratio": 1.0,
            }
        }
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager.effective_settings",
            lambda s: s,
        )
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
        assert "688008" in watch_codes

    def test_sell_respects_lock(self, portfolio, snapshot, settings_enabled, monkeypatch):
        from datetime import date

        monkeypatch.setattr(
            "agent_reach.daily_run.trade_calendar.today_shanghai",
            lambda: date(2026, 8, 21),
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager.effective_settings",
            lambda s: s,
        )
        settings_enabled.setdefault("trading", {})["holding_lock_days"] = 1
        portfolio["holdings"][0]["days_held"] = 0
        portfolio["holdings"][0]["acquired_date"] = "2026-08-21"
        portfolio["holdings"][1]["days_held"] = 5
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
        assert "688008" in result.message or "T+1" in result.message or "锁" in result.message
        assert len(result.portfolio["holdings"]) == 2

    def test_same_day_buy_blocks_sell_t_plus_one(self, portfolio, snapshot, settings_enabled, monkeypatch):
        from datetime import date

        settings_enabled["harness_runtime"] = {
            "deep_loss_policy": {
                "loss_cny_threshold": 5000,
                "loss_pct_threshold": 10,
                "cover_ratio": 0.0,
                "sell_ratio": 1.0,
                "non_deep_loss_sell_ratio": 1.0,
            }
        }
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager.effective_settings",
            lambda s: s,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.trade_calendar.today_shanghai",
            lambda: date(2026, 8, 21),
        )
        snapshot = dict(snapshot)
        snapshot["code"] = "002273"
        portfolio = dict(portfolio)
        portfolio["trade_session_date"] = "2026-08-21"
        portfolio["holdings"] = [
            {
                "code": "002273",
                "name": "水晶光电",
                "shares": 800,
                "cost": 30.0,
                "days_held": 5,
                "acquired_date": "2026-08-01",
            }
        ]
        buy = TradeDecision(
            action="buy",
            trade_id="T12",
            lookback_mss=55.0,
            lookback_detail=[],
            trend="rising",
            reasoning="MSS 建仓",
        )
        bought = apply_auto_adjust(portfolio, buy, snapshot, settings_enabled, cash_limit_bypass=True)
        assert bought.applied is True
        holding = bought.portfolio["holdings"][0]
        assert holding["today_buy_shares"] == bought.actions[0].shares
        assert holding["shares"] == 800 + bought.actions[0].shares

        sell = TradeDecision(
            action="sell",
            trade_id="T13",
            lookback_mss=49.0,
            lookback_detail=[],
            trend="mixed",
            reasoning="防御性减仓",
        )
        sold = apply_auto_adjust(bought.portfolio, sell, snapshot, settings_enabled)
        assert sold.applied is True
        sold_shares = sold.actions[0].shares
        assert sold_shares <= 800
        assert sold_shares < bought.actions[0].shares

    def test_buy_merges_cost_with_commission(self, portfolio, snapshot, settings_enabled, monkeypatch):
        from datetime import date

        monkeypatch.setattr(
            "agent_reach.daily_run.trade_calendar.today_shanghai",
            lambda: date(2026, 8, 21),
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.pnl_execution_guard.pnl_buy_block_reason",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.pnl_execution_guard.pnl_symbol_ledger_block_reason",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager.pnl_buy_block_reason",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager.pnl_symbol_ledger_block_reason",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager.effective_settings",
            lambda s: s,
        )
        snapshot = dict(snapshot)
        snapshot["code"] = "002273"
        portfolio = dict(portfolio)
        portfolio["holdings"] = [
            {
                "code": "002273",
                "name": "水晶光电",
                "shares": 300,
                "cost": 33.81,
                "days_held": 5,
                "acquired_date": "2026-08-01",
            }
        ]
        decision = TradeDecision(
            action="buy",
            trade_id="T12",
            lookback_mss=55.0,
            lookback_detail=[],
            trend="rising",
            reasoning="加仓",
        )
        result = apply_auto_adjust(
            portfolio,
            decision,
            snapshot,
            settings_enabled,
            cash_limit_bypass=True,
        )
        assert result.applied is True
        action = result.actions[0]
        holding = result.portfolio["holdings"][0]
        old_basis = 300 * 33.81
        new_basis = old_basis + action.amount + action.commission
        expected_cost = round(new_basis / holding["shares"], 4)
        assert holding["cost"] == expected_cost

    def test_sell_deep_loss_blocked_when_cover_insufficient(self, portfolio, snapshot, settings_enabled, tmp_path, monkeypatch):
        portfolio = {
            "total": 186000,
            "cash": 75000,
            "holdings": [
                {
                    "code": "002583",
                    "name": "海能达",
                    "shares": 1000,
                    "cost": 19.38,
                    "price": 8.32,
                    "days_held": 30,
                },
                {
                    "code": "600584",
                    "name": "长电科技",
                    "shares": 800,
                    "cost": 80.8,
                    "price": 85.0,
                    "days_held": 5,
                },
            ],
            "watchlist": [],
        }
        snapshot = {
            "code": "002583",
            "price": 8.32,
            "portfolio": portfolio,
            "watchlist": [],
        }
        settings_enabled.setdefault("pnl_overview", {})["deep_loss_sell_require_cover"] = True
        settings_enabled.setdefault("pnl_overview", {})["plan_trim_exempt_cover"] = False
        settings_enabled.setdefault("pnl_overview", {})["defensive_trim_exempt_cover"] = False
        ledger = tmp_path / "trade_ledger.jsonl"
        ledger.write_text("", encoding="utf-8")
        monkeypatch.setattr("agent_reach.daily_run.realized_pnl.default_ledger_path", lambda: ledger)

        decision = TradeDecision(
            action="sell",
            trade_id="T1",
            lookback_mss=35.0,
            lookback_detail=[],
            trend="falling",
            reasoning="防御性减仓",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_enabled)
        assert result.applied is False
        assert "深度套牢" in result.message
        assert "不足" in result.message
        assert len(result.portfolio["holdings"]) == 2

    def test_sell_deep_loss_partial_when_allowed(self, settings_enabled, tmp_path, monkeypatch):
        portfolio = {
            "total": 186000,
            "cash": 75000,
            "holdings": [
                {
                    "code": "002583",
                    "name": "海能达",
                    "shares": 1000,
                    "cost": 19.38,
                    "price": 8.32,
                    "days_held": 30,
                },
                {
                    "code": "600584",
                    "name": "长电科技",
                    "shares": 800,
                    "cost": 80.8,
                    "price": 120.0,
                    "days_held": 5,
                },
            ],
            "watchlist": [],
        }
        snapshot = {
            "code": "002583",
            "price": 8.32,
            "portfolio": portfolio,
            "watchlist": [],
        }
        settings_enabled.setdefault("pnl_overview", {})["deep_loss_sell_require_cover"] = True
        settings_enabled.setdefault("pnl_overview", {})["plan_trim_exempt_cover"] = False
        settings_enabled.setdefault("pnl_overview", {})["defensive_trim_exempt_cover"] = False
        settings_enabled["harness_runtime"] = {
            "deep_loss_policy": {
                "loss_cny_threshold": 5000,
                "loss_pct_threshold": 10,
                "cover_ratio": 0.8,
                "sell_ratio": 0.5,
            }
        }
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager.effective_settings",
            lambda s: s,
        )
        ledger = tmp_path / "trade_ledger.jsonl"
        ledger.write_text(
            '{"at":"2026-08-01T00:00:00+00:00","actions":[{"side":"sell","code":"688008","shares":100,"price":300,"amount":30000,"commission":45,"realized_pnl":5000}]}\n',
            encoding="utf-8",
        )
        monkeypatch.setattr("agent_reach.daily_run.realized_pnl.default_ledger_path", lambda: ledger)

        decision = TradeDecision(
            action="sell",
            trade_id="T1",
            lookback_mss=35.0,
            lookback_detail=[],
            trend="falling",
            reasoning="防御性减仓",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_enabled)
        assert result.applied is True
        assert result.actions[0].code == "002583"
        assert result.actions[0].shares == 500
        remaining = next(h for h in result.portfolio["holdings"] if h["code"] == "002583")
        assert remaining["shares"] == 500

    def test_sell_non_deep_loss_partial_when_ratio_below_one(self, settings_enabled, tmp_path, monkeypatch):
        portfolio = {
            "total": 100000,
            "cash": 50000,
            "holdings": [
                {
                    "code": "600584",
                    "name": "长电科技",
                    "shares": 800,
                    "cost": 80.8,
                    "price": 85.0,
                    "days_held": 5,
                },
            ],
            "watchlist": [],
        }
        snapshot = {
            "code": "600584",
            "price": 85.0,
            "portfolio": portfolio,
            "watchlist": [],
        }
        settings_enabled["harness_runtime"] = {
            "deep_loss_policy": {
                "loss_cny_threshold": 5000,
                "loss_pct_threshold": 10,
                "non_deep_loss_sell_ratio": 0.5,
            }
        }
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager.effective_settings",
            lambda s: s,
        )
        ledger = tmp_path / "trade_ledger.jsonl"
        ledger.write_text("", encoding="utf-8")
        monkeypatch.setattr("agent_reach.daily_run.realized_pnl.default_ledger_path", lambda: ledger)

        decision = TradeDecision(
            action="sell",
            trade_id="T1",
            lookback_mss=35.0,
            lookback_detail=[],
            trend="falling",
            reasoning="防御性减仓",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_enabled)
        assert result.applied is True
        assert result.actions[0].code == "600584"
        assert result.actions[0].shares == 400
        assert len(result.portfolio["holdings"]) == 1
        assert result.portfolio["holdings"][0]["shares"] == 400

    def test_coverable_gains_uses_realized_weight(self, tmp_path, monkeypatch):
        from agent_reach.daily_run.portfolio_manager import portfolio_coverable_gains

        portfolio = {
            "holdings": [
                {"code": "600584", "name": "长电", "shares": 100, "cost": 80, "price": 90},
            ],
        }
        enriched = {"600584": {"price": 90}}
        settings = {
            "harness_runtime": {
                "deep_loss_policy": {"coverable_realized_weight": 0.5},
            }
        }
        ledger = tmp_path / "trade_ledger.jsonl"
        ledger.write_text(
            "\n".join(
                [
                    '{"at":"2026-07-01T00:00:00+00:00","actions":[{"side":"buy","code":"688008","shares":100,"price":250,"amount":25000,"commission":37.5}]}',
                    '{"at":"2026-08-01T00:00:00+00:00","actions":[{"side":"sell","code":"688008","shares":100,"price":300,"amount":30000,"commission":45,"realized_pnl":5000}]}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("agent_reach.daily_run.realized_pnl.default_ledger_path", lambda: ledger)
        coverable = portfolio_coverable_gains(
            portfolio, enriched, settings, exclude_code="002583"
        )
        assert 3400 <= coverable <= 3600
        assert coverable < 5000.0

    def test_sell_deep_loss_allowed_when_cover_sufficient(self, portfolio, snapshot, settings_enabled, tmp_path, monkeypatch):
        portfolio = {
            "total": 186000,
            "cash": 75000,
            "holdings": [
                {
                    "code": "002583",
                    "name": "海能达",
                    "shares": 1000,
                    "cost": 19.38,
                    "price": 8.32,
                    "days_held": 30,
                },
                {
                    "code": "600584",
                    "name": "长电科技",
                    "shares": 800,
                    "cost": 80.8,
                    "price": 120.0,
                    "days_held": 5,
                },
            ],
            "watchlist": [],
        }
        snapshot = {
            "code": "002583",
            "price": 8.32,
            "portfolio": portfolio,
            "watchlist": [],
        }
        settings_enabled.setdefault("pnl_overview", {})["deep_loss_sell_require_cover"] = True
        settings_enabled.setdefault("pnl_overview", {})["plan_trim_exempt_cover"] = False
        settings_enabled.setdefault("pnl_overview", {})["defensive_trim_exempt_cover"] = False
        ledger = tmp_path / "trade_ledger.jsonl"
        ledger.write_text(
            '{"at":"2026-08-01T00:00:00+00:00","actions":[{"side":"sell","code":"688008","shares":100,"price":300,"amount":30000,"commission":45,"realized_pnl":5000}]}\n',
            encoding="utf-8",
        )
        monkeypatch.setattr("agent_reach.daily_run.realized_pnl.default_ledger_path", lambda: ledger)

        decision = TradeDecision(
            action="sell",
            trade_id="T1",
            lookback_mss=35.0,
            lookback_detail=[],
            trend="falling",
            reasoning="防御性减仓",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_enabled)
        assert result.applied is True
        assert result.actions[0].code == "002583"

    def test_buy_from_watchlist(self, portfolio, snapshot, settings_enabled):
        snapshot = dict(snapshot)
        snapshot["code"] = "000725"
        snapshot["price"] = 7.63
        snapshot["name"] = "京东方A"
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
        assert result.actions[0].code == "000725"
        assert len(result.portfolio["holdings"]) == 3
        assert result.portfolio["cash"] < portfolio["cash"]

    def test_buy_decision_symbol_when_already_held(self, portfolio, snapshot, settings_enabled):
        """Decision symbol may be bought even when already in holdings (add to position)."""
        snapshot = dict(snapshot)
        snapshot["code"] = "002273"
        snapshot["price"] = 32.04
        snapshot["name"] = "水晶光电"

        decision = TradeDecision(
            action="buy",
            trade_id="T1",
            lookback_mss=55.0,
            lookback_detail=[],
            trend="rising",
            reasoning="MSS 达阈值",
        )
        before_shares = next(h["shares"] for h in portfolio["holdings"] if h["code"] == "002273")
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_enabled)
        assert result.applied is True
        assert result.actions[0].code == "002273"
        held = next(h for h in result.portfolio["holdings"] if h["code"] == "002273")
        assert held["shares"] > before_shares
        assert len(result.portfolio["holdings"]) == 2

    def test_buy_does_not_fallback_when_decision_symbol_unaffordable(
        self, portfolio, snapshot, settings_enabled
    ):
        """When the decision symbol cannot afford one lot, do not buy another watchlist name."""
        portfolio = dict(portfolio)
        portfolio["cash"] = 52000
        portfolio["cash_ratio"] = 0.52
        portfolio["total"] = 100000
        snapshot = dict(snapshot)
        snapshot["portfolio"] = dict(snapshot["portfolio"])
        snapshot["portfolio"]["cash"] = 52000
        snapshot["portfolio"]["cash_ratio"] = 0.52
        snapshot["portfolio"]["total"] = 100000
        settings_enabled.setdefault("thresholds", {})["min_cash_ratio"] = 0.48

        decision = TradeDecision(
            action="buy",
            trade_id="T1",
            lookback_mss=55.0,
            lookback_detail=[],
            trend="rising",
            reasoning="MSS 达阈值",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_enabled)
        assert result.applied is False
        assert "688008" in result.message
        assert "不足一手" in result.message

    def test_max_total_blocks_buy_when_full(self, portfolio, snapshot, settings_enabled):
        # apply_auto_adjust only ever gates new buys via max_total_symbols
        # (portfolio.max_holdings is evolved/reported but not enforced here),
        # so the cap under test must be max_total_symbols.
        settings_enabled["portfolio"]["max_holdings"] = 4
        settings_enabled["portfolio"]["max_total_symbols"] = 4
        portfolio["holdings"] = [
            {"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87, "days_held": 5},
            {"code": "002273", "name": "水晶光电", "shares": 300, "cost": 33.81, "days_held": 5},
            {"code": "603986", "name": "兆易创新", "shares": 100, "cost": 600.0, "days_held": 5},
            {"code": "000725", "name": "京东方A", "shares": 1000, "cost": 7.5, "days_held": 5},
        ]
        portfolio["watchlist"] = [{"code": "300308", "name": "中际旭创"}]
        snapshot = dict(snapshot)
        snapshot["code"] = "300308"
        snapshot["price"] = 320.0
        snapshot["name"] = "中际旭创"
        snapshot["watchlist"] = portfolio["watchlist"]
        snapshot["portfolio"] = dict(portfolio)
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
        assert "合计上限" in result.message

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


class TestRoundLot:
    """M5: STAR (688) board partial-sell must round UP to a lot, not down to 0."""

    def test_main_board_below_lot_no_total_shares_returns_zero(self):
        from agent_reach.daily_run.portfolio_manager import _round_lot

        assert _round_lot("600584", 50) == 0

    def test_main_board_partial_sell_below_lot_rounds_up(self):
        from agent_reach.daily_run.portfolio_manager import _round_lot

        # 175/350: below one 100-share lot, but the position holds several lots.
        assert _round_lot("600584", 40, total_shares=350) == 100

    def test_star_board_partial_sell_below_lot_rounds_up(self):
        from agent_reach.daily_run.portfolio_manager import _round_lot

        # 35% of 350 = 122, below the 200-share STAR lot but position has >=1 lot.
        assert _round_lot("688008", 122, total_shares=350) == 200

    def test_star_board_odd_lot_position_sells_in_full(self):
        from agent_reach.daily_run.portfolio_manager import _round_lot

        # Holding itself (100 shares) is below the 200-share lot: only a full
        # odd-lot exit is valid, never 0.
        assert _round_lot("688008", 35, total_shares=100) == 100

    def test_full_exit_bypasses_lot_rounding(self):
        from agent_reach.daily_run.portfolio_manager import _round_lot

        assert _round_lot("688008", 350, total_shares=350) == 350

    def test_buy_sizing_unaffected_rounds_down(self):
        """Buy-sizing calls (no total_shares) must keep rounding DOWN, never up."""
        from agent_reach.daily_run.portfolio_manager import _round_lot

        assert _round_lot("688008", 350) == 200
        assert _round_lot("600584", 150) == 100


class TestTradabilityGate:
    """H1/M3/M4: auto paper trades must not fill through limit-up/down or suspension."""

    def test_sell_blocked_at_limit_down(self, portfolio, snapshot, settings_enabled, monkeypatch):
        settings_enabled["harness_runtime"] = {
            "deep_loss_policy": {
                "loss_cny_threshold": 5000,
                "loss_pct_threshold": 10,
                "cover_ratio": 0.0,
                "sell_ratio": 1.0,
                "non_deep_loss_sell_ratio": 1.0,
            }
        }
        monkeypatch.setattr("agent_reach.daily_run.portfolio_manager.effective_settings", lambda s: s)
        snapshot = dict(snapshot)
        snapshot["code"] = "002273"
        snapshot["portfolio"] = dict(snapshot["portfolio"])
        holdings = [dict(h) for h in snapshot["portfolio"]["holdings"]]
        for h in holdings:
            if h["code"] == "002273":
                h["change_pct"] = -9.95  # main board 10% limit
        snapshot["portfolio"]["holdings"] = holdings

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
        assert "跌停" in result.message
        assert len(result.portfolio["holdings"]) == 2

    def test_sell_allowed_when_not_at_limit(self, portfolio, snapshot, settings_enabled, monkeypatch):
        settings_enabled["harness_runtime"] = {
            "deep_loss_policy": {
                "loss_cny_threshold": 5000,
                "loss_pct_threshold": 10,
                "cover_ratio": 0.0,
                "sell_ratio": 1.0,
                "non_deep_loss_sell_ratio": 1.0,
            }
        }
        monkeypatch.setattr("agent_reach.daily_run.portfolio_manager.effective_settings", lambda s: s)
        snapshot = dict(snapshot)
        snapshot["code"] = "002273"
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

    def test_buy_blocked_at_limit_up(self, portfolio, snapshot, settings_enabled):
        snapshot = dict(snapshot)
        snapshot["code"] = "000725"
        snapshot["price"] = 7.63
        snapshot["change_pct"] = 9.95  # main board 10% limit
        decision = TradeDecision(
            action="buy",
            trade_id="T1",
            lookback_mss=55.0,
            lookback_detail=[],
            trend="rising",
            reasoning="MSS 达阈值",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_enabled, cash_limit_bypass=True)
        assert result.applied is False
        assert "涨停" in result.message
        assert len(result.portfolio["holdings"]) == 2

    def test_buy_blocked_when_suspended(self, portfolio, snapshot, settings_enabled):
        snapshot = dict(snapshot)
        snapshot["code"] = "000725"
        snapshot["price"] = 7.63
        snapshot["change_pct"] = 0.0
        snapshot["volume"] = 0
        decision = TradeDecision(
            action="buy",
            trade_id="T1",
            lookback_mss=55.0,
            lookback_detail=[],
            trend="rising",
            reasoning="MSS 达阈值",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_enabled, cash_limit_bypass=True)
        assert result.applied is False
        assert "停牌" in result.message

    def test_buy_allowed_when_not_at_limit(self, portfolio, snapshot, settings_enabled):
        snapshot = dict(snapshot)
        snapshot["code"] = "000725"
        snapshot["price"] = 7.63
        snapshot["change_pct"] = 0.66
        decision = TradeDecision(
            action="buy",
            trade_id="T1",
            lookback_mss=55.0,
            lookback_detail=[],
            trend="rising",
            reasoning="MSS 达阈值",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_enabled, cash_limit_bypass=True)
        assert result.applied is True


class TestIncrementDays:
    def test_sync_without_acquired_date_keeps_counter(self, portfolio):
        updated = increment_holding_days(portfolio)
        assert updated["holdings"][0]["days_held"] == 5

    def test_sync_from_acquired_date_t_plus_one(self):
        from datetime import date
        from unittest.mock import patch

        from agent_reach.daily_run.portfolio_manager import holding_is_sellable, sync_portfolio_holding_days

        pf = {"holdings": [{"code": "000725", "shares": 100, "acquired_date": "2026-07-24", "days_held": 0}]}
        with patch("agent_reach.daily_run.trade_calendar.today_shanghai", return_value=date(2026, 7, 24)):
            assert holding_is_sellable(pf["holdings"][0], {"trading": {"holding_lock_days": 1}}) is False
        with patch("agent_reach.daily_run.trade_calendar.today_shanghai", return_value=date(2026, 7, 27)):
            synced = sync_portfolio_holding_days(pf)
            assert synced["holdings"][0]["days_held"] == 1
            assert holding_is_sellable(synced["holdings"][0], {"trading": {"holding_lock_days": 1}}) is True

    def test_today_buy_lock_resets_on_new_trade_session(self):
        from datetime import date
        from unittest.mock import patch

        from agent_reach.daily_run.portfolio_manager import holding_sellable_shares, sync_portfolio_holding_days

        pf = {
            "trade_session_date": "2026-08-21",
            "holdings": [
                {
                    "code": "002273",
                    "shares": 500,
                    "today_buy_shares": 500,
                    "acquired_date": "2026-08-21",
                }
            ],
        }
        with patch("agent_reach.daily_run.trade_calendar.today_shanghai", return_value=date(2026, 8, 21)):
            assert holding_sellable_shares(pf["holdings"][0]) == 0
        with patch("agent_reach.daily_run.trade_calendar.today_shanghai", return_value=date(2026, 8, 22)):
            synced = sync_portfolio_holding_days(pf)
            assert synced["holdings"][0]["today_buy_shares"] == 0
            assert holding_sellable_shares(synced["holdings"][0]) == 500

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


class TestAppliedTradesTodayScope:
    """M7: schedule.max_applied_trades_per_day_scope opt-in per-symbol cap."""

    def _register(self, code: str, n: int = 1) -> None:
        from agent_reach.daily_run.portfolio_manager import TradeAction, register_applied_trade

        for i in range(n):
            register_applied_trade(
                [
                    TradeAction(
                        side="buy",
                        code=code,
                        name=code,
                        shares=100 + i,
                        price=10.0,
                        amount=1000.0 + i,
                        commission=1.0,
                        reasoning="test",
                    )
                ]
            )

    def test_global_scope_counts_across_symbols(self):
        from agent_reach.daily_run.portfolio_manager import applied_trades_today_for

        self._register("000725", 2)
        self._register("600584", 1)
        settings = {"schedule": {"max_applied_trades_per_day_scope": "global"}}
        assert applied_trades_today_for("000725", settings) == 3
        assert applied_trades_today_for("600584", settings) == 3

    def test_default_scope_is_global(self):
        from agent_reach.daily_run.portfolio_manager import applied_trades_today_for

        self._register("000725", 2)
        self._register("600584", 1)
        assert applied_trades_today_for("000725", {}) == 3

    def test_per_symbol_scope_isolates_counts(self):
        from agent_reach.daily_run.portfolio_manager import applied_trades_today_for

        self._register("000725", 2)
        self._register("600584", 1)
        settings = {"schedule": {"max_applied_trades_per_day_scope": "per_symbol"}}
        assert applied_trades_today_for("000725", settings) == 2
        assert applied_trades_today_for("600584", settings) == 1
        assert applied_trades_today_for("002273", settings) == 0

    def test_symbol_trades_today_direct(self):
        from agent_reach.daily_run.portfolio_manager import symbol_trades_today

        self._register("000725", 3)
        assert symbol_trades_today("000725") == 3
        assert symbol_trades_today("600584") == 0


class TestRecalcTotalsPricePrecedence:
    """H2: `_recalc_totals` must mark to the freshest `enriched` quote, not a
    holding's own possibly-stale embedded `price` (e.g. snapshot_builder's
    `enrich_holding` stamps a holding's `price` earlier in the same close run,
    before close_portfolio_summary re-fetches a fresher quote into `enriched`).
    This mirrors the precedence `_holding_unrealized_pnl` already uses via its
    `{**holding, **enriched.get(code, {})}` merge, so total/cash_ratio mark to
    the same price as per-holding P&L rows elsewhere in the same close card."""

    def test_prefers_enriched_price_over_stale_holding_price(self):
        from agent_reach.daily_run.portfolio_manager import _recalc_totals

        pf = {
            "cash": 10000.0,
            "holdings": [
                {"code": "000725", "name": "京东方A", "shares": 1000, "price": 5.0, "cost": 4.0},
            ],
        }
        # enriched carries a fresher quote (8.0) than the holding's own stale
        # embedded price (5.0, captured earlier in the same run).
        enriched = {"000725": {"price": 8.0}}
        _recalc_totals(pf, enriched)

        assert pf["total"] == 18000.0  # 10000 cash + 1000 * 8.0, not 5.0
        assert round(pf["cash_ratio"], 4) == round(10000.0 / 18000.0, 4)

    def test_falls_back_to_holding_price_when_enriched_missing(self):
        from agent_reach.daily_run.portfolio_manager import _recalc_totals

        pf = {
            "cash": 10000.0,
            "holdings": [
                {"code": "000725", "name": "京东方A", "shares": 1000, "price": 5.0, "cost": 4.0},
            ],
        }
        _recalc_totals(pf, {})

        assert pf["total"] == 15000.0  # 10000 cash + 1000 * 5.0 (own price)

    def test_falls_back_to_cost_when_no_price_anywhere(self):
        from agent_reach.daily_run.portfolio_manager import _recalc_totals

        pf = {
            "cash": 10000.0,
            "holdings": [{"code": "000725", "name": "京东方A", "shares": 1000, "cost": 4.0}],
        }
        _recalc_totals(pf, {})

        assert pf["total"] == 14000.0  # 10000 cash + 1000 * 4.0 (cost fallback)


class TestBuyBudgetContext:
    def test_negative_cash_blocks_with_clear_message(self):
        from agent_reach.daily_run.portfolio_manager import ApplyResult, _buy_budget_context

        pf = {
            "total": -77586.72,
            "cash": -121117.72,
            "holdings": [
                {"code": "688008", "shares": 100, "cost": 205.16, "price": 205.16},
                {"code": "002583", "shares": 2500, "cost": 8.51, "price": 8.51},
            ],
        }
        enriched = {
            "688008": {"price": 205.16},
            "002583": {"price": 8.51},
        }
        settings = {
            "thresholds": {"min_cash_ratio": 0.5},
            "portfolio": {"min_deploy_cash": 1000},
        }
        result = _buy_budget_context(pf, enriched, settings, pf["holdings"])
        assert isinstance(result, ApplyResult)
        assert "账户现金为负" in result.message
        assert "可部署现金 -" not in result.message

    def test_low_deployable_never_shows_negative_amount(self):
        from agent_reach.daily_run.portfolio_manager import ApplyResult, _buy_budget_context

        pf = {
            "total": 100_000,
            "cash": 10_000,
            "holdings": [{"code": "688008", "shares": 100, "cost": 900, "price": 900}],
        }
        enriched = {"688008": {"price": 900}}
        settings = {
            "thresholds": {"min_cash_ratio": 0.5},
            "portfolio": {"min_deploy_cash": 1000},
        }
        result = _buy_budget_context(pf, enriched, settings, pf["holdings"])
        assert isinstance(result, ApplyResult)
        assert result.message.startswith("可部署现金 ¥0")
        assert "-86494" not in result.message


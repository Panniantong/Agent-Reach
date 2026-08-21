# -*- coding: utf-8
"""Tests for PnL execution-layer buy/sell blocks."""

from agent_reach.daily_run.intraday import TradeDecision, _decide_trade
from agent_reach.daily_run.pnl_execution_guard import (
    pnl_buy_block_reason,
    pnl_symbol_ledger_block_reason,
)
from agent_reach.daily_run.portfolio_manager import apply_auto_adjust


def _settings(**overrides):
    base = {
        "pnl_overview": {
            "win_rate_min": 0.0,
            "loss_streak_max": 0,
            "ledger_cost_tolerance_cny": 0.01,
        },
        "harness_runtime": {
            "deep_loss_policy": {
                "win_rate_min": 0.33,
                "loss_streak_max": 3,
                "ledger_cost_tolerance_cny": 0.01,
            }
        },
        "portfolio": {"auto_adjust_enabled": True, "max_holdings": 10},
        "trading": {"holding_lock_days": 0, "commission_rate": 0.0015},
        "thresholds": {"min_cash_ratio": 0.2},
    }
    base.update(overrides)
    return base


def test_watchlist_remove_low_win_rate_reason():
    from agent_reach.daily_run.pnl_execution_guard import watchlist_remove_low_win_rate_reason

    reason = watchlist_remove_low_win_rate_reason(
        _settings(),
        "002273",
        overview={
            "realized_sells": [
                {"code": "002273", "name": "水晶光电", "realized_pnl": -4.35},
                {"code": "002273", "name": "水晶光电", "realized_pnl": -4.07},
                {"code": "002273", "name": "水晶光电", "realized_pnl": -10.0},
            ]
        },
    )
    assert reason is not None
    assert "移出观察池" in reason


def test_pnl_buy_block_on_loss_streak():
    reason = pnl_buy_block_reason(
        _settings(pnl_overview={"win_rate_min": 0, "loss_streak_max": 3}),
        overview={
            "win_count": 2,
            "loss_count": 3,
            "realized_sells": [
                {"realized_pnl": 100},
                {"realized_pnl": -100},
                {"realized_pnl": -80},
                {"realized_pnl": -50},
            ],
        },
    )
    assert reason is not None
    assert "连亏警戒" in reason


def test_pnl_buy_block_on_low_win_rate():
    reason = pnl_buy_block_reason(
        _settings(),
        overview={
            "win_count": 1,
            "loss_count": 4,
            "realized_sells": [
                {"code": "603986", "name": "兆易创新", "realized_pnl": 100},
                {"code": "603986", "name": "兆易创新", "realized_pnl": -10},
                {"code": "603986", "name": "兆易创新", "realized_pnl": -20},
                {"code": "603986", "name": "兆易创新", "realized_pnl": -30},
            ],
        },
        code="603986",
    )
    assert reason is not None
    assert "603986" in reason
    assert "卖出胜率偏低" in reason


def test_pnl_buy_block_ignores_other_symbols_win_rate():
    reason = pnl_buy_block_reason(
        _settings(),
        overview={
            "win_count": 1,
            "loss_count": 4,
            "realized_sells": [
                {"code": "688008", "name": "澜起科技", "realized_pnl": -10},
                {"code": "688008", "name": "澜起科技", "realized_pnl": -20},
                {"code": "688008", "name": "澜起科技", "realized_pnl": -30},
                {"code": "688008", "name": "澜起科技", "realized_pnl": -40},
                {"code": "600584", "name": "长电科技", "realized_pnl": 3496.54},
            ],
        },
        code="600584",
    )
    assert reason is None


def test_pnl_buy_block_requires_symbol_code_for_win_rate():
    reason = pnl_buy_block_reason(
        _settings(),
        overview={
            "win_count": 1,
            "loss_count": 4,
            "realized_sells": [{"code": "603986", "realized_pnl": -10}],
        },
    )
    assert reason is None


def test_pnl_ledger_block_on_holding():
    reason = pnl_symbol_ledger_block_reason(
        _settings(),
        "000001",
        portfolio={
            "holdings": [{"code": "000001", "name": "测试", "shares": 100, "cost": 0}],
        },
    )
    assert reason is not None
    assert "ledger 缺买入成本" in reason


def test_apply_buy_blocked_by_loss_streak():
    portfolio = {
        "total": 100000,
        "cash": 61000,
        "holdings": [],
        "watchlist": [{"code": "603986", "name": "兆易创新"}],
    }
    snapshot = {
        "code": "603986",
        "portfolio": portfolio,
        "watchlist": [{"code": "603986", "name": "兆易创新", "price": 100.0}],
    }
    settings = _settings(
        pnl_overview={"win_rate_min": 0, "loss_streak_max": 3},
        harness_runtime={
            "deep_loss_policy": {
                "win_rate_min": 0,
                "loss_streak_max": 3,
                "ledger_cost_tolerance_cny": 0.01,
            }
        },
    )
    decision = TradeDecision(
        action="buy",
        trade_id="T1",
        lookback_mss=60.0,
        lookback_detail=[],
        trend="rising",
        reasoning="test",
    )

    from agent_reach.daily_run import pnl_execution_guard

    original = pnl_execution_guard._pnl_overview_for_portfolio
    pnl_execution_guard._pnl_overview_for_portfolio = lambda _pf: {
        "win_count": 1,
        "loss_count": 3,
        "realized_sells": [
            {"realized_pnl": 100},
            {"realized_pnl": -100},
            {"realized_pnl": -80},
            {"realized_pnl": -50},
        ],
    }
    try:
        result = apply_auto_adjust(portfolio, decision, snapshot, settings)
    finally:
        pnl_execution_guard._pnl_overview_for_portfolio = original

    assert result.applied is False
    assert "连亏警戒" in result.message


def test_decide_trade_blocks_buy_on_pnl_guard():
    settings = _settings(
        harness_runtime={
            "deep_loss_policy": {
                "win_rate_min": 0.33,
                "loss_streak_max": 3,
                "ledger_cost_tolerance_cny": 0.01,
            }
        }
    )
    snapshot = {
        "code": "603986",
        "portfolio": {"total": 100000, "cash": 61000, "cash_ratio": 0.61, "holdings": []},
    }
    report = {"code": "603986", "name": "兆易创新", "blocked": False}

    class Verdict:
        blocked = False
        verdict = "ok"
        mss_final = 70.0

    from agent_reach.daily_run import pnl_execution_guard

    original = pnl_execution_guard._pnl_overview_for_portfolio
    pnl_execution_guard._pnl_overview_for_portfolio = lambda _pf: {
        "win_count": 1,
        "loss_count": 4,
        "realized_sells": [
            {"code": "603986", "name": "兆易创新", "realized_pnl": 100},
            {"code": "603986", "name": "兆易创新", "realized_pnl": -10},
            {"code": "603986", "name": "兆易创新", "realized_pnl": -20},
            {"code": "603986", "name": "兆易创新", "realized_pnl": -30},
        ],
    }
    try:
        decision = _decide_trade(
            lookback_mss=60.0,
            trend="rising",
            verdict=Verdict(),
            report=report,
            snapshot=snapshot,
            settings=settings,
            trade_index=1,
            expected_return_pct=0.02,
        )
    finally:
        pnl_execution_guard._pnl_overview_for_portfolio = original

    assert decision.action == "hold"
    assert decision.blocked is True
    assert "卖出胜率偏低" in decision.reasoning

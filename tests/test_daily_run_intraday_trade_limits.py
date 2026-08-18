# -*- coding: utf-8
"""Tests for intraday trade evaluation vs applied trade limits."""

import json

import pytest

from agent_reach.daily_run.intraday import (
    IntradayState,
    TradeDecision,
    append_trade_skip_note,
    apply_paper_trade,
    explain_trade_skip_reason,
    max_applied_trades_per_day,
    max_trade_evaluations_per_symbol,
    should_evaluate_trade,
)
from agent_reach.daily_run.portfolio_manager import apply_auto_adjust, save_daily_trade_state
from agent_reach.daily_run.settings import load_settings


@pytest.fixture
def portfolio():
    return {
        "total": 100000,
        "cash": 61000,
        "cash_ratio": 0.61,
        "holdings": [
            {"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87, "days_held": 5},
        ],
        "watchlist": [
            {"code": "600584", "name": "长电科技"},
            {"code": "002415", "name": "海康威视"},
            {"code": "603986", "name": "兆易创新"},
        ],
    }


@pytest.fixture
def settings_trade_limits():
    s = load_settings()
    s.setdefault("schedule", {})
    s["schedule"]["max_applied_trades_per_day"] = 5
    s["schedule"]["max_trade_evaluations_per_symbol"] = 8
    s["schedule"]["trade_min_scans"] = 3
    s["schedule"]["trade_every_n_scans"] = 2
    s.setdefault("portfolio", {})["auto_adjust_enabled"] = True
    return s


def _scan(mss: float, scan_id: str = "S1") -> dict:
    return {
        "scan_id": scan_id,
        "mss_final": mss,
        "verdict": "可做",
        "code": "600584",
        "name": "长电科技",
    }


class TestTradeLimitHelpers:
    def test_defaults(self, settings_trade_limits):
        assert max_applied_trades_per_day(settings_trade_limits) == 5
        assert max_trade_evaluations_per_symbol(settings_trade_limits) == 8

    def test_should_evaluate_when_applied_cap_full_but_eval_slots_remain(self, settings_trade_limits):
        st = IntradayState(
            date="2026-08-18",
            scans=[_scan(56, f"S{i}") for i in range(1, 12)],
            trades=[{"trade_id": f"T{i}", "action": "hold"} for i in range(1, 6)],
        )
        save_daily_trade_state({"date": "2026-08-18", "fingerprints": [f"f{i}" for i in range(5)]})
        assert should_evaluate_trade(st, settings_trade_limits) is True

    def test_should_not_evaluate_when_eval_cap_full(self, settings_trade_limits):
        st = IntradayState(
            date="2026-08-18",
            scans=[_scan(56, f"S{i}") for i in range(1, 10)],
            trades=[{"trade_id": f"T{i}", "action": "hold"} for i in range(1, 9)],
        )
        assert should_evaluate_trade(st, settings_trade_limits) is False
        reason = explain_trade_skip_reason(st, settings_trade_limits)
        assert "评估已达上限" in reason

    def test_append_trade_skip_note(self):
        md = append_trade_skip_note("**S12 数据收集完成**", "今日全组合落账已达上限 5 次")
        assert "未调仓评估" in md
        assert "落账已达上限" in md


class TestBuyPreferSignalCode:
    def test_buy_prefers_snapshot_code(self, portfolio, settings_trade_limits):
        snapshot = {
            "code": "600584",
            "portfolio": portfolio,
            "watchlist": [
                {"code": "600584", "name": "长电科技", "price": 84.0, "change_pct": 1.0},
                {"code": "002415", "name": "海康威视", "price": 35.0, "change_pct": 3.0},
            ],
        }
        decision = TradeDecision(
            action="buy",
            trade_id="T1",
            lookback_mss=56.0,
            lookback_detail=[],
            trend="rising",
            reasoning="MSS 达阈值",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings_trade_limits)
        assert result.applied is True
        assert result.actions[0].code == "600584"

    def test_apply_paper_trade_blocks_when_global_applied_cap_full(
        self, portfolio, monkeypatch, tmp_path, settings_trade_limits
    ):
        portfolio_path = tmp_path / "portfolio.json"
        portfolio_path.write_text(json.dumps(portfolio, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(
            "agent_reach.daily_run.snapshot_builder.default_portfolio_path",
            lambda: portfolio_path,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager.daily_trade_state_path",
            lambda: tmp_path / "daily_trade_state.json",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager._today_str",
            lambda: "2026-08-18",
        )
        save_daily_trade_state({"date": "2026-08-18", "fingerprints": [f"f{i}" for i in range(5)]})

        snapshot = {
            "code": "600584",
            "portfolio": portfolio,
            "watchlist": portfolio["watchlist"],
        }
        decision = TradeDecision(
            action="buy",
            trade_id="T6",
            lookback_mss=56.0,
            lookback_detail=[],
            trend="rising",
            reasoning="MSS 达阈值",
        )
        result = apply_paper_trade(decision, snapshot, settings=settings_trade_limits)
        assert result.applied is False
        assert "落账已达上限" in result.message

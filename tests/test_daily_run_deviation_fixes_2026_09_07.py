# -*- coding: utf-8
"""Regression tests for 2026-09-07 deviation attribution fixes."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from agent_reach.daily_run.defensive_trim_guards import (
    defensive_trim_blocked_by_strength,
    defensive_trim_cfg,
)
from agent_reach.daily_run.harness import HarnessEntry, HarnessState
from agent_reach.daily_run.harness_policy import resolve_harness_position_policy
from agent_reach.daily_run.intraday import _decide_trade
from agent_reach.daily_run.portfolio_manager import deep_loss_sell_analysis
from agent_reach.daily_run.session_regime import (
    merged_session_regime,
    supportive_regime_active,
)
from agent_reach.daily_run.verdict import VerdictResult
from agent_reach.daily_run.watchlist_breakout import evaluate_watchlist_breakout_buy


def _base_settings(**overrides):
    settings = {
        "thresholds": {"macro_veto": 30, "aggressive_entry": 45, "min_cash_ratio": 0.15},
        "trading": {
            "commission_rate": 0.0015,
            "slippage_rate": 0.001,
            "holding_lock_days": 1,
            "friction_min_return_pct": 0.001,
        },
        "harness": {
            "enabled": True,
            "runtime_overlay": True,
            "runtime_rejected_guard": False,
            "position_evolution": {"deploy_ratio": "harness", "max_position_pct": "harness"},
        },
        "harness_runtime": {
            "session_seed": {"merged_regime": "supportive"},
            "trend_policy": {
                "buy_trends": ["rising", "turning_up", "mixed", "flat"],
                "sell_trends": ["falling", "turning_down"],
            },
            "deep_loss_policy": {
                "loss_cny_threshold": 5000,
                "loss_pct_threshold": 10,
                "cover_ratio": 1.0,
                "sell_ratio": 0.5,
                "non_deep_loss_sell_ratio": 0.7,
                "supportive_reallocation_cover_ratio": 0.35,
                "supportive_reallocation_sell_ratio": 0.1,
            },
        },
        "intraday": {"watchlist_breakout": {"enabled": True, "max_position_pct": 5.0}},
        "pnl_overview": {
            "plan_trim_exempt_cover": False,
            "defensive_trim_exempt_cover": False,
        },
    }
    settings.update(overrides)
    return settings


class TestSessionRegime:
    def test_merged_session_regime_from_seed(self):
        settings = {"harness_runtime": {"session_seed": {"merged_regime": "supportive"}}}
        assert merged_session_regime(settings) == "supportive"
        assert supportive_regime_active(settings) is True

    def test_supportive_regime_defaults_neutral(self):
        assert merged_session_regime({}) == "neutral"
        assert supportive_regime_active({}) is False


class TestWatchlistBreakout:
    def test_eligible_after_1400_on_strong_watchlist_mover(self):
        now = datetime(2026, 9, 7, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        snapshot = {
            "portfolio": {"holdings": [], "cash_ratio": 0.46},
            "watchlist": [{"code": "300308", "name": "中际旭创", "change_pct": 10.38}],
        }
        report = {"code": "300308", "name": "中际旭创", "blocked": False}
        result = evaluate_watchlist_breakout_buy(
            snapshot=snapshot,
            report=report,
            settings=_base_settings(),
            lookback_mss=48.87,
            trend="mixed",
            aggressive_entry=45.0,
            now=now,
        )
        assert result.eligible is True
        assert result.max_position_pct == pytest.approx(5.0)
        assert "观察池突破" in result.reason

    def test_decide_trade_buys_despite_observe_verdict_when_breakout(self):
        now = datetime(2026, 9, 7, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        settings = _base_settings()
        verdict = VerdictResult(
            verdict="观察",
            confidence="中",
            mss_final=48,
            entry_price=None,
            stop_loss_price=None,
            invalidation="",
            reasoning="",
            blocked=True,
        )
        snapshot = {
            "as_of": "2026-09-07T06:30:00+00:00",
            "portfolio": {
                "cash_ratio": 0.46,
                "cash": 460_000,
                "total_value": 1_000_000,
                "holdings": [],
            },
            "watchlist": [{"code": "300308", "name": "中际旭创", "change_pct": 10.38, "price": 120.0}],
            "symbols": [{"code": "300308", "price": 120.0, "change_pct": 10.38}],
        }
        decision = _decide_trade(
            lookback_mss=48.87,
            trend="mixed",
            verdict=verdict,
            report={"code": "300308", "name": "中际旭创", "blocked": True},
            snapshot=snapshot,
            settings=settings,
            trade_index=1,
            expected_return_pct=0.01,
            prior_trades=[],
        )
        assert decision.action == "buy"
        assert decision.blocked is False
        assert decision.watchlist_breakout is True
        assert decision.max_position_pct_override == pytest.approx(5.0)


class TestSupportiveDeployFloor:
    def test_supportive_raises_deploy_ratio_after_defensive_trim_cap(self):
        state = HarnessState()
        state.entries["memory"]["miss"] = HarnessEntry(
            id="miss",
            kind="memory",
            title="miss",
            content="MSS 预测偏离",
            source="deterministic",
            job="close",
            evidence="close",
            created_at="2026-09-06T00:00:00+00:00",
            updated_at="2026-09-06T00:00:00+00:00",
        )
        settings = _base_settings(
            harness={
                "enabled": True,
                "runtime_overlay": True,
                "runtime_overlay_sources": ["memory"],
                "position_evolution": {"deploy_ratio": "harness", "max_position_pct": "harness"},
            }
        )
        pos = resolve_harness_position_policy(state, settings=settings)
        assert pos["deploy_ratio"] == pytest.approx(0.35)
        assert pos["max_position_pct"] == pytest.approx(30.0)

    def test_supportive_deploy_floor_without_defensive_trim(self):
        settings = _base_settings(
            harness={
                "enabled": True,
                "runtime_overlay": False,
                "position_evolution": {"deploy_ratio": "harness", "max_position_pct": "harness"},
            },
            harness_runtime={
                "session_seed": {"merged_regime": "supportive"},
                "trade_signals": {},
            },
        )
        pos = resolve_harness_position_policy(HarnessState(), settings=settings)
        assert pos["deploy_ratio"] >= 0.5


class TestDefensiveTrimStrengthDefault:
    def test_default_max_symbol_change_pct_is_three(self):
        cfg = defensive_trim_cfg({})
        assert cfg["max_symbol_change_pct"] == pytest.approx(3.0)

    def test_moderate_gain_allows_trim_with_three_pct_default(self):
        reason = defensive_trim_blocked_by_strength(
            {},
            trend="mixed",
            code="688008",
            snapshot={
                "portfolio": {
                    "holdings": [{"code": "688008", "name": "澜起科技", "change_pct": 2.5}]
                }
            },
        )
        assert reason is None

    def test_lanqi_plus_539_still_blocks_trim_with_three_pct_default(self):
        reason = defensive_trim_blocked_by_strength(
            {},
            trend="mixed",
            code="688008",
            snapshot={
                "portfolio": {
                    "holdings": [{"code": "688008", "name": "澜起科技", "change_pct": 5.39}]
                }
            },
        )
        assert reason is not None
        assert "5.39" in reason


class TestSupportiveDeepLossReallocation:
    def test_supportive_lowers_cover_and_allows_partial_sell(self):
        settings = _base_settings()
        pf = {
            "holdings": [
                {
                    "code": "600584",
                    "name": "长电科技",
                    "shares": 5000,
                    "cost": 20.0,
                    "price": 30.0,
                }
            ]
        }
        holding = {
            "code": "002583",
            "name": "海能达",
            "shares": 10_000,
            "cost": 12.0,
            "days_held": 30,
        }
        enriched = {
            "002583": {"price": 8.0},
            "600584": {"price": 30.0},
        }
        analysis = deep_loss_sell_analysis(pf, holding, enriched, settings)
        assert analysis["cover_ratio"] == pytest.approx(0.35)
        assert analysis["sell_ratio"] >= 0.1
        assert analysis["allowed"] is True

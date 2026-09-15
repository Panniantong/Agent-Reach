# -*- coding: utf-8
"""Tests for harness-evolved intraday policy guards."""

import pytest

from agent_reach.daily_run.intraday import _decide_trade
from agent_reach.daily_run.intraday_harness import intraday_to_harness_evidence
from agent_reach.daily_run.intraday_policy import (
    detect_mss_trend,
    estimate_expected_return,
    intraday_audit_block_reason,
    kronos_buy_block_reason,
    trend_allows_buy,
    trend_allows_defensive_sell,
)
from agent_reach.daily_run.lookback import detect_mss_trend as lookback_detect


class TestTrendPolicy:
    def test_detect_trend_turning_up(self):
        scans = [{"mss_final": 40}, {"mss_final": 45}, {"mss_final": 52}]
        assert detect_mss_trend(scans, {"intraday": {"trend_delta_threshold": 1.0}}) == "turning_up"

    def test_higher_delta_threshold_flattens_trend(self):
        scans = [{"mss_final": 40}, {"mss_final": 45}, {"mss_final": 52}]
        settings = {
            "harness": {"enabled": False},
            "intraday": {"trend_delta_threshold": 8.0},
        }
        assert detect_mss_trend(scans, settings) == "rising"

    def test_buy_trends_from_runtime(self):
        settings = {
            "harness_runtime": {
                "trend_policy": {"buy_trends": ["rising"], "sell_trends": ["falling"]},
            }
        }
        assert trend_allows_buy(settings, "rising") is True
        assert trend_allows_buy(settings, "turning_up") is False
        assert trend_allows_defensive_sell(settings, "falling") is True

    def test_lookback_reexports_detect(self):
        scans = [{"mss_final": 40}, {"mss_final": 45}, {"mss_final": 52}]
        assert lookback_detect(scans) == "turning_up"


class TestExpectedReturnPolicy:
    def test_estimate_from_runtime(self):
        settings = {
            "harness_runtime": {
                "expected_return_policy": {
                    "exp_return_base": 0.02,
                    "exp_return_slope": 0.002,
                    "exp_return_veto": -0.03,
                    "exp_return_neutral": 0.006,
                }
            }
        }
        assert estimate_expected_return(55.0, 50.0, 40.0, settings) == pytest.approx(0.03, abs=0.0001)
        assert estimate_expected_return(35.0, 50.0, 40.0, settings) == pytest.approx(-0.03, abs=0.0001)


class TestIntradayGuards:
    def test_audit_block_when_enabled(self):
        settings = {"harness_runtime": {"intraday_audit_policy": {"intraday_block_on_audit_fail": 1.0}}}
        reason = intraday_audit_block_reason(settings, {"audit_passed": False})
        assert reason is not None
        assert "审计" in reason

    def test_kronos_bearish_blocks_buy(self):
        settings = {
            "intraday": {"kronos_bearish_block_buy": True},
            "harness_runtime": {"kronos_bearish": {"688008": 2.5}},
        }
        reason = kronos_buy_block_reason(settings, "688008")
        assert reason is not None
        assert "Kronos" in reason

    def test_decide_trade_blocks_kronos_bearish(self):
        class Verdict:
            blocked = False
            verdict = "ok"
            mss_final = 70.0

        settings = {
            "thresholds": {"macro_veto": 40, "aggressive_entry": 50, "min_cash_ratio": 0.2},
            "trading": {"friction_min_return_pct": 0.001},
            "schedule": {"trade_min_scans": 2},
            "intraday": {"kronos_bearish_block_buy": True},
            "harness_runtime": {
                "trend_policy": {
                    "buy_trends": ["rising", "turning_up"],
                    "sell_trends": ["falling"],
                    "trend_min_points": 2,
                    "trend_delta_threshold": 1.0,
                },
                "expected_return_policy": {
                    "exp_return_base": 0.015,
                    "exp_return_slope": 0.001,
                    "exp_return_veto": -0.02,
                    "exp_return_neutral": 0.005,
                },
                "kronos_bearish": {"688008": 3.0},
                "deep_loss_policy": {
                    "win_rate_min": 0,
                    "loss_streak_max": 0,
                    "ledger_cost_tolerance_cny": 0.01,
                },
            },
        }
        decision = _decide_trade(
            lookback_mss=60.0,
            trend="rising",
            verdict=Verdict(),
            report={"code": "688008", "name": "澜起", "blocked": False, "audit_passed": True},
            snapshot={"code": "688008", "portfolio": {"cash_ratio": 0.6, "holdings": []}},
            settings=settings,
            trade_index=1,
            expected_return_pct=0.02,
        )
        assert decision.action == "hold"
        assert decision.blocked is True
        assert "Kronos" in decision.reasoning


class TestIntradayHarnessEvidence:
    def test_buy_budget_block_skips_miss_apply_harness_signal(self):
        ev = intraday_to_harness_evidence(
            {
                "scan": {"scan_id": "S5", "code": "603986", "name": "兆易创新", "mss_final": 55},
                "trend": "rising",
                "lookback_mss": 52,
                "trade": {
                    "decision": {
                        "action": "buy",
                        "trend": "rising",
                        "lookback_mss": 52,
                        "blocked": True,
                        "block_kind": "buy_budget",
                        "reasoning": (
                            "603986 可部署买入预算 ¥1,712 不足一手"
                            "（100 股 @ ¥388.77 ≈ ¥39,000）；MSS 达进攻阈值"
                        ),
                    }
                },
            }
        )
        assert not any("达进攻阈值未落账" in item for item in ev["memory"] + ev["policy"])
        assert not any("可部署现金不足" in item for item in ev["policy"])

    def test_friction_and_trend_policy_phrases(self):
        ev = intraday_to_harness_evidence(
            {
                "scan": {"scan_id": "S5", "code": "688008", "name": "澜起", "mss_final": 55},
                "trend": "mixed",
                "lookback_mss": 52,
                "trade": {
                    "decision": {
                        "action": "hold",
                        "trend": "mixed",
                        "lookback_mss": 52,
                        "friction_blocked": True,
                        "reasoning": "MSS 达 55 但摩擦成本过高",
                    }
                },
            }
        )
        assert any("摩擦成本过高" in p for p in ev["policy"])
        assert any("趋势误判" in p for p in ev["policy"])
        assert any("正面摩擦" in p for p in ev["playbook"])

    def test_mss_verdict_hit_recorded_in_playbook(self):
        ev = intraday_to_harness_evidence(
            {
                "scans": [
                    {"scan_id": "S3", "verdict": "可做", "prediction_hit": True, "mss_final": 55},
                    {"scan_id": "S4", "verdict": "可做", "prediction_hit": True, "mss_final": 54},
                    {"scan_id": "S5", "verdict": "可做", "prediction_hit": False, "mss_final": 53},
                ],
                "scan": {"scan_id": "S5", "code": "688008", "name": "澜起", "mss_final": 53},
            }
        )
        assert any("MSS「可做」命中 2/3" in m for m in ev["memory"])
        assert any("勿因单日偏差过度收紧" in p for p in ev["playbook"])

    def test_harness_trend_evolution_on_miss(self):
        from agent_reach.daily_run.harness import HarnessEntry, HarnessState
        from agent_reach.daily_run.harness_policy import resolve_harness_trend_policy

        state = HarnessState()
        state.entries["policy"]["early"] = HarnessEntry(
            id="early",
            kind="policy",
            title="过早买入",
            content="过早买入：turning_up 摩擦阻断，提高 trend_min_points",
            source="deterministic",
            job="intraday",
            evidence="intraday",
            created_at="2026-08-18T00:00:00+00:00",
            updated_at="2026-08-18T00:00:00+00:00",
        )
        policy = resolve_harness_trend_policy(
            state,
            settings={"harness": {"runtime_overlay_sources": ["policy"]}, "intraday": {}},
        )
        assert policy["trend_min_points"] >= 3.0
        assert policy["buy_trends"] == ["rising"]


class TestEvalTrendPolicy:
    def test_should_evaluate_respects_eval_trends(self):
        from agent_reach.daily_run.intraday import should_evaluate_trade, IntradayState

        settings = {
            "harness": {"enabled": False},
            "schedule": {"intraday_trade_enabled": True, "trade_min_scans": 2, "trade_every_n_scans": 5},
            "intraday": {"eval_trends": ["rising"]},
        }
        st = IntradayState(
            date="2026-08-18",
            scans=[
                {"scan_id": "S1", "mss_final": 40},
                {"scan_id": "S2", "mss_final": 41},
                {"scan_id": "S3", "mss_final": 42},
            ],
            trades=[],
        )
        assert should_evaluate_trade(st, settings) is True

        st_flat = IntradayState(
            date="2026-08-18",
            scans=[
                {"scan_id": "S1", "mss_final": 50},
                {"scan_id": "S2", "mss_final": 50},
            ],
            trades=[],
        )
        assert should_evaluate_trade(st_flat, settings) is False


class TestKronosBullishRelax:
    def test_effective_aggressive_entry_lowers_on_bullish(self):
        from agent_reach.daily_run.intraday_policy import effective_aggressive_entry

        settings = {
            "intraday": {"kronos_bullish_relax_buy": True, "kronos_bullish_entry_pts": 3.0},
            "harness_runtime": {"kronos_bullish": {"688008": 2.5}},
        }
        aggressive = effective_aggressive_entry(settings, "688008", 50.0, macro_veto=40.0)
        assert aggressive == pytest.approx(47.0)


class TestMinDeployAndFriction:
    def test_min_deploy_evolution_on_loss_streak(self):
        from agent_reach.daily_run.harness import HarnessEntry, HarnessState
        from agent_reach.daily_run.harness_policy import resolve_harness_min_deploy_policy

        state = HarnessState()
        state.entries["policy"]["streak"] = HarnessEntry(
            id="streak",
            kind="policy",
            title="连亏",
            content="连亏警戒：连续3笔卖出亏损",
            source="deterministic",
            job="pnl_overview",
            evidence="pnl",
            created_at="2026-08-18T00:00:00+00:00",
            updated_at="2026-08-18T00:00:00+00:00",
        )
        policy = resolve_harness_min_deploy_policy(
            state,
            settings={"harness": {"runtime_overlay_sources": ["policy"]}, "portfolio": {"min_deploy_cash": 1000}},
        )
        assert policy["min_deploy_cash"] >= 2000.0

    def test_effective_friction_hurdle_includes_round_trip(self):
        from agent_reach.daily_run.intraday_policy import effective_friction_hurdle

        hurdle = effective_friction_hurdle(
            {
                "harness": {"enabled": False},
                "trading": {"commission_rate": 0.002, "slippage_rate": 0.001, "friction_min_return_pct": 0.003},
            }
        )
        assert hurdle >= 0.006


class TestTradeBlockMessages:
    def test_deep_loss_block_shows_sell_not_buy(self, tmp_path, monkeypatch):
        from agent_reach.daily_run.intraday import (
            TradeDecision,
            format_trade_block_message,
            render_intraday_trade_markdown,
        )
        from agent_reach.daily_run.verdict import VerdictResult

        ledger = tmp_path / "trade_ledger.jsonl"
        ledger.write_text("", encoding="utf-8")
        monkeypatch.setattr("agent_reach.daily_run.realized_pnl.default_ledger_path", lambda: ledger)

        settings = {
            "thresholds": {"macro_veto": 30, "aggressive_entry": 45, "min_cash_ratio": 0.5},
            "trading": {"commission_rate": 0.0015, "slippage_rate": 0.001, "holding_lock_days": 1},
            "pnl_overview": {
                "deep_loss_sell_require_cover": True,
                "large_unrealized_loss_cny": 5000,
                "plan_trim_exempt_cover": False,
                "defensive_trim_exempt_cover": False,
            },
            "harness_runtime": {"trade_signals": {"defensive_trim": True}},
        }
        verdict = VerdictResult(
            verdict="观察",
            confidence="中",
            mss_final=54,
            entry_price=None,
            stop_loss_price=None,
            invalidation="",
            reasoning="",
            blocked=False,
        )
        decision = _decide_trade(
            lookback_mss=45.0,
            trend="falling",
            verdict=verdict,
            report={"code": "002583", "name": "海能达", "blocked": False},
            snapshot={
                "code": "002583",
                "price": 8.32,
                "portfolio": {
                    "cash_ratio": 0.75,
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
                },
            },
            settings=settings,
            trade_index=3,
            expected_return_pct=0.01,
        )
        assert decision.action == "hold"
        assert decision.block_kind == "sell_deep_loss"

        message = format_trade_block_message(decision)
        assert message is not None
        assert "不允许卖出" in message
        assert "不允许执行买入" not in message
        assert "不允许买入" not in message

        markdown = render_intraday_trade_markdown(decision, [], {}, [])
        assert "T3 · 观望" in markdown
        assert "不允许卖出" in markdown
        assert "不允许执行买入" not in markdown

    def test_infer_block_kind_from_legacy_reasoning(self):
        from agent_reach.daily_run.intraday import format_trade_block_message, infer_trade_block_kind

        legacy = {
            "blocked": True,
            "reasoning": "防御性减仓信号触发，但海能达 深度套牢（浮亏 ¥11,300 / 58.3%），暂不卖",
        }
        assert infer_trade_block_kind(legacy) == "sell_deep_loss"
        message = format_trade_block_message(legacy)
        assert message is not None
        assert "不允许卖出" in message

    def test_verdict_block_shows_buy_message(self):
        from agent_reach.daily_run.intraday import format_trade_block_message

        decision = {
            "blocked": True,
            "block_kind": "buy_verdict",
            "reasoning": "标签 观察 阻断买入（即时 MSS 47）",
        }
        message = format_trade_block_message(decision)
        assert message is not None
        assert "不允许买入" in message
        assert "不允许卖出" not in message

    def test_defensive_trim_block_shows_recovery_message(self):
        from agent_reach.daily_run.intraday import format_trade_block_message

        decision = {
            "blocked": True,
            "block_kind": "sell_defensive_trim",
            "reasoning": "Lookback MSS 52 ≥ 回暖线 50，记忆 MSS 偏离暂不执行防御减仓",
        }
        message = format_trade_block_message(decision)
        assert message is not None
        assert "回暖" in message
        assert "防御减仓" in message
        assert "不允许买入" not in message

    def test_buy_budget_block_shows_deploy_footer(self):
        from agent_reach.daily_run.intraday import (
            TradeDecision,
            format_trade_block_message,
            render_intraday_trade_markdown,
        )
        from agent_reach.daily_run.portfolio_manager import ApplyResult, render_apply_markdown

        settings = {
            "thresholds": {"macro_veto": 30, "aggressive_entry": 45, "min_cash_ratio": 0.5},
            "trading": {"commission_rate": 0.0015, "slippage_rate": 0.001},
            "portfolio": {"min_deploy_cash": 1000},
            "harness_runtime": {
                "position_policy": {"deploy_ratio": 0.25, "max_position_pct": 25.0},
            },
        }
        snapshot = {
            "code": "603986",
            "name": "兆易创新",
            "price": 388.77,
            "portfolio": {
                "total": 98561.92,
                "cash": 56130.92,
                "cash_ratio": 0.5695,
                "holdings": [
                    {"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87, "days_held": 5},
                ],
                "watchlist": [{"code": "603986", "name": "兆易创新"}],
            },
            "watchlist": [{"code": "603986", "name": "兆易创新", "price": 388.77}],
        }
        decision = TradeDecision(
            action="buy",
            trade_id="T4",
            lookback_mss=48.0,
            lookback_detail=[],
            trend="rising",
            reasoning="603986 可部署买入预算 ¥1,712 不足一手（100 股 @ ¥388.77 ≈ ¥39,000）",
            blocked=True,
            block_kind="buy_budget",
        )
        markdown = render_intraday_trade_markdown(
            decision,
            [],
            {"code": "603986", "name": "兆易创新"},
            [],
            settings=settings,
            enriched=snapshot,
        )
        assert "部署预算" in markdown
        assert "deploy_ratio 25%" in markdown
        assert "本笔预算" in markdown
        assert "一手约" in markdown

        message = format_trade_block_message(decision)
        assert message is not None
        assert "本笔预算 ¥1,712" in message
        assert "约 ¥39,000" in message

        apply_md = render_apply_markdown(
            ApplyResult(applied=False, portfolio=snapshot["portfolio"], message="决策 hold，不调仓"),
            decision=decision,
        )
        assert "预算预检阻断" in apply_md
        assert "决策 hold" not in apply_md


class TestDefensiveTrimPolicy:
    def test_defensive_trim_requires_mss_buffer(self):
        from agent_reach.daily_run.intraday_policy import defensive_trim_allows_sell

        settings = {
            "harness_runtime": {
                "defensive_trim_policy": {
                    "defensive_trim_min_mss": 40.0,
                    "defensive_trim_mss_buffer": 5.0,
                },
                "trend_policy": {"sell_trends": ["falling"]},
            }
        }
        assert defensive_trim_allows_sell(settings, lookback_mss=44.0, macro_veto=40.0, trend="falling") is False
        assert defensive_trim_allows_sell(settings, lookback_mss=46.0, macro_veto=40.0, trend="falling") is True

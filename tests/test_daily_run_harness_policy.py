# -*- coding: utf-8
"""Tests for harness policy runtime overlay."""

from agent_reach.daily_run.harness import HarnessEntry, HarnessState
from agent_reach.daily_run.harness_policy import (
    aggressive_entry_default,
    apply_harness_policy_overlay,
    harness_symbol_score,
    harness_buy_budget,
    kronos_score_adjustment,
    macro_veto_default,
    resolve_harness_position_policy,
    resolve_harness_symbol_bias,
    resolve_harness_symbol_score_weights,
    resolve_harness_flat_overrides,
    resolve_harness_kronos_bias,
    resolve_harness_lookback_weights,
    resolve_harness_mss_weights,
    resolve_harness_threshold_overrides,
    resolve_harness_trade_signals,
    friction_min_return_default,
    forecast_int_default,
    threshold_default,
)
from agent_reach.daily_run.intraday import _decide_trade, _passes_friction
from agent_reach.daily_run.portfolio_manager import _symbol_score
from agent_reach.daily_run.settings import effective_settings
from agent_reach.daily_run.skill_rejected import add_rejected_strategy, trade_blocked_by_rejected
from agent_reach.daily_run.verdict import VerdictResult


def _state_with_policy(entry_id: str, *, title: str, content: str) -> HarnessState:
    state = HarnessState()
    state.entries["policy"][entry_id] = HarnessEntry(
        id=entry_id,
        kind="policy",
        title=title,
        content=content,
        source="test",
        job="forecast",
        evidence="test",
        created_at="2026-08-17T00:00:00+00:00",
        updated_at="2026-08-17T00:00:00+00:00",
    )
    return state


def _harness_settings(**overrides: object) -> dict:
    base = {
        "thresholds": {"max_snapshot_age_hours": 24},
        "harness": {
            "enabled": True,
            "runtime_overlay": True,
            "threshold_evolution_mode": "harness",
            "runtime_overlay_sources": ["policy", "memory"],
        },
    }
    base.update(overrides)
    return base


class TestHarnessPolicyOverlay:
    def test_harness_mode_no_explicit_policy_uses_neutral_defaults(self):
        state = HarnessState()
        effective = resolve_harness_threshold_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=_harness_settings(),
        )
        assert effective["macro_veto"] == 40.0
        assert effective["aggressive_entry"] == 50.0
        assert effective["min_cash_ratio"] == 0.0
        assert effective["max_price_deviation_pct"] == 0.08

    def test_harness_mode_offensive_memory_lowers_cash(self):
        state = HarnessState()
        state.entries["memory"]["offense"] = HarnessEntry(
            id="offense",
            kind="memory",
            title="宏观回暖",
            content="宏观回暖：下日进入进攻期，降低现金比例",
            source="deterministic",
            job="weekly",
            evidence="weekly",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        effective = resolve_harness_threshold_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=_harness_settings(),
        )
        assert effective["min_cash_ratio"] == 0.25
        assert effective["macro_veto"] == 38.0
        assert effective["aggressive_entry"] == 52.0

    def test_fixed_mode_keeps_config_floor(self):
        state = HarnessState()
        effective = resolve_harness_threshold_overrides(
            state,
            {
                "macro_veto": 40,
                "aggressive_entry": 50,
                "min_cash_ratio": 0.4,
                "max_price_deviation_pct": 0.08,
                "max_snapshot_age_hours": 24,
            },
            settings={
                "harness": {
                    "threshold_evolution_mode": "fixed",
                    "runtime_overlay_sources": [],
                }
            },
        )
        assert effective["macro_veto"] == 40.0
        assert effective["min_cash_ratio"] == 0.4

    def test_harness_signal_evolution_sets_defensive_floor(self):
        state = HarnessState()
        state.entries["memory"]["dev"] = HarnessEntry(
            id="dev",
            kind="memory",
            title="偏差",
            content="偏差：价格变动 23.7% 超过锚点阈值 8.0%",
            source="deterministic",
            job="forecast",
            evidence="forecast",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        effective = resolve_harness_threshold_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=_harness_settings(),
        )
        assert effective["macro_veto"] == 30.0
        assert effective["aggressive_entry"] == 45.0
        assert effective["min_cash_ratio"] == 0.5
        assert effective["max_price_deviation_pct"] == 0.06

    def test_structured_macro_veto_policy(self):
        state = _state_with_policy(
            "forecast_policy_macro_veto",
            title="宏观一票否决执行规则",
            content="MSS<30，现金比例≥50%",
        )
        effective = resolve_harness_threshold_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=_harness_settings(),
        )
        assert effective["macro_veto"] == 30.0
        assert effective["min_cash_ratio"] == 0.5

    def test_structured_deviation_policy(self):
        state = _state_with_policy(
            "forecast_policy_deviation_threshold",
            title="偏差阈值",
            content="当预测标的收盘价格变动绝对值超过锚点阈值8.0%时，触发偏差记录",
        )
        effective = resolve_harness_threshold_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=_harness_settings(),
        )
        assert effective["max_price_deviation_pct"] == 0.08

    def test_memory_lowers_aggressive_entry(self):
        state = HarnessState()
        state.entries["memory"]["mss_miss"] = HarnessEntry(
            id="mss_miss",
            kind="memory",
            title="MSS 预测偏离",
            content="MSS 预测偏离：下日调低进攻阈值或缩窄仓位",
            source="deterministic",
            job="close",
            evidence="close",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        effective = resolve_harness_threshold_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=_harness_settings(),
        )
        assert effective["aggressive_entry"] == 45.0

    def test_effective_settings_applies_overlay(self, monkeypatch):
        state = _state_with_policy(
            "forecast_policy_macro_veto",
            title="宏观一票否决执行规则",
            content="维持现金比例≥50%",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.harness.load_harness",
            lambda: state,
        )
        cfg = effective_settings(_harness_settings())
        assert cfg["thresholds"]["macro_veto"] == 30.0
        assert cfg["thresholds"]["min_cash_ratio"] == 0.5
        assert "threshold_overlay" in cfg.get("harness_runtime", {})

    def test_overlay_disabled_passthrough(self, monkeypatch):
        state = _state_with_policy(
            "forecast_policy_macro_veto",
            title="宏观一票否决执行规则",
            content="MSS<30",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.harness.load_harness",
            lambda: state,
        )
        cfg = apply_harness_policy_overlay(
            {
                "thresholds": {
                    "macro_veto": 40,
                    "aggressive_entry": 50,
                    "max_snapshot_age_hours": 24,
                },
                "harness": {"enabled": True, "runtime_overlay": False},
            }
        )
        assert cfg["thresholds"]["macro_veto"] == 40

    def test_threshold_default_before_overlay(self, monkeypatch):
        from agent_reach.daily_run.harness import HarnessState

        monkeypatch.setattr(
            "agent_reach.daily_run.harness.load_harness",
            lambda: HarnessState(),
        )
        settings = _harness_settings()
        assert threshold_default(settings, "macro_veto") == 40.0
        assert threshold_default(settings, "max_price_deviation_pct") == 0.08

    def test_threshold_default_ignores_static_macro_veto_when_harness_evolved(self, monkeypatch):
        state = HarnessState()
        state.entries["memory"]["dev"] = HarnessEntry(
            id="dev",
            kind="memory",
            title="偏差",
            content="偏差：价格变动 23.7% 超过锚点阈值 8.0%",
            source="deterministic",
            job="forecast",
            evidence="forecast",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.harness.load_harness",
            lambda: state,
        )
        settings = _harness_settings(
            thresholds={"macro_veto": 40, "aggressive_entry": 50, "max_snapshot_age_hours": 24},
        )
        assert threshold_default(settings, "macro_veto") == 30.0
        assert macro_veto_default(settings) == 30.0

    def test_harness_mode_runtime_neutral_defaults(self):
        state = HarnessState()
        flat = resolve_harness_flat_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=_harness_settings(),
        )
        assert flat["trade_min_scans"] == 3.0
        assert flat["trade_every_n_scans"] == 2.0
        assert flat["max_applied_trades_per_day"] == 5.0
        assert flat["max_trade_evaluations_per_symbol"] == 8.0
        assert flat["max_holdings"] == 10.0
        assert flat["max_total_symbols"] == 15.0
        assert flat["holding_lock_days"] == 1.0
        assert flat["stop_loss_ma20_pct"] == 0.04

    def test_defensive_runtime_evolution(self):
        state = HarnessState()
        state.entries["memory"]["dev"] = HarnessEntry(
            id="dev",
            kind="memory",
            title="偏差",
            content="偏差：价格变动 23.7% 超过锚点阈值 8.0%",
            source="deterministic",
            job="forecast",
            evidence="forecast",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        flat = resolve_harness_flat_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=_harness_settings(),
        )
        assert flat["max_holdings"] == 5.0
        assert flat["max_total_symbols"] == 10.0
        assert flat["holding_lock_days"] == 2.0
        assert flat["stop_loss_ma20_pct"] == 0.05
        assert flat["trade_min_scans"] == 2.0
        assert flat["max_applied_trades_per_day"] == 3.0
        assert flat["max_trade_evaluations_per_symbol"] == 6.0

    def test_offensive_memory_raises_trade_limits(self):
        state = HarnessState()
        state.entries["memory"]["offense"] = HarnessEntry(
            id="offense",
            kind="memory",
            title="进攻期",
            content="宏观回暖进入进攻期，适度提高落账与评估槽",
            source="deterministic",
            job="weekly",
            evidence="weekly",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        flat = resolve_harness_flat_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=_harness_settings(),
        )
        assert flat["max_applied_trades_per_day"] == 6.0
        assert flat["max_trade_evaluations_per_symbol"] == 10.0

    def test_applied_cap_memory_tightens_limit(self):
        state = HarnessState()
        state.entries["memory"]["cap"] = HarnessEntry(
            id="cap",
            kind="memory",
            title="落账",
            content="落账已达上限：全组合 paper apply 次数过多",
            source="deterministic",
            job="intraday",
            evidence="intraday",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        flat = resolve_harness_flat_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=_harness_settings(),
        )
        assert flat["max_applied_trades_per_day"] == 3.0

    def test_aggressive_entry_miss_memory_lowers_threshold(self):
        state = HarnessState()
        state.entries["memory"]["miss"] = HarnessEntry(
            id="miss",
            kind="memory",
            title="未落账",
            content="达进攻阈值未落账：MSS 达标但未成交",
            source="deterministic",
            job="intraday",
            evidence="intraday",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        flat = resolve_harness_flat_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=_harness_settings(),
        )
        assert flat["aggressive_entry"] == 49.0
        assert flat["trade_min_scans"] == 2.0

    def test_aggressive_entry_default_helper(self, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.harness.load_harness",
            lambda: HarnessState(),
        )
        assert aggressive_entry_default(_harness_settings()) == 50.0

    def test_scan_sparse_lookback_weights(self):
        state = HarnessState()
        state.entries["playbook"]["scan"] = HarnessEntry(
            id="scan",
            kind="playbook",
            title="扫描偏少",
            content="1 天盘中扫描偏少 — intraday 次数 <5",
            source="deterministic",
            job="weekly",
            evidence="weekly",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        settings = _harness_settings()
        settings["harness"]["runtime_overlay_sources"] = ["policy", "memory", "playbook"]
        flat = resolve_harness_flat_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=settings,
        )
        weights = resolve_harness_lookback_weights(state, settings=settings, flat=flat)
        assert weights == [0.6, 0.25, 0.15]

    def test_effective_settings_applies_runtime_sections(self, monkeypatch):
        state = _state_with_policy(
            "forecast_policy_macro_veto",
            title="宏观一票否决执行规则",
            content="维持现金比例≥50%",
        )
        state.entries["playbook"]["scan_sparse"] = HarnessEntry(
            id="scan_sparse",
            kind="playbook",
            title="扫描偏少",
            content="1 天盘中扫描偏少 — intraday 次数 <5",
            source="deterministic",
            job="weekly",
            evidence="weekly",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        settings = _harness_settings()
        settings["harness"]["runtime_overlay_sources"] = ["policy", "playbook"]
        monkeypatch.setattr(
            "agent_reach.daily_run.harness.load_harness",
            lambda: state,
        )
        cfg = effective_settings(settings)
        assert cfg["portfolio"]["max_holdings"] == 5
        assert cfg["trading"]["holding_lock_days"] == 2
        assert cfg["schedule"]["trade_min_scans"] == 3
        assert cfg["schedule"]["max_applied_trades_per_day"] == 5
        assert cfg["schedule"]["max_trade_evaluations_per_symbol"] == 8
        assert cfg["lookback_weights"] == [0.6, 0.25, 0.15]
        assert "lookback_overlay" in cfg.get("harness_runtime", {})
        assert "runtime_overlay" in cfg.get("harness_runtime", {})


class TestHarnessRuntimeExtensions:
    def test_mss_weights_down_on_deviation_memory(self):
        state = HarnessState()
        state.entries["memory"]["dev"] = HarnessEntry(
            id="dev",
            kind="memory",
            title="经验规则",
            content="偏差：价格变动 23.7% 超过锚点阈值 8.0%",
            source="deterministic",
            job="forecast",
            evidence="forecast",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        base = {"fx": 0.2, "flow": 0.2, "technical": 0.15, "quant": 0.1, "risk": 0.05}
        effective = resolve_harness_mss_weights(
            state,
            base,
            settings={"harness": {"runtime_overlay_sources": ["memory"]}},
        )
        base_share = base["technical"] / sum(base.values())
        eff_share = effective["technical"] / sum(effective.values())
        assert eff_share < base_share
        assert effective["quant"] / sum(effective.values()) < base["quant"] / sum(base.values())

    def test_mss_weights_defensive_trim_boosts_macro(self):
        state = HarnessState()
        state.entries["memory"]["miss"] = HarnessEntry(
            id="miss",
            kind="memory",
            title="盈亏目标未达",
            content="盈亏目标未达：目标 +100 实际 +0",
            source="deterministic",
            job="close",
            evidence="close",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        base = {
            "fx": 0.2,
            "flow": 0.2,
            "global": 0.15,
            "sentiment": 0.15,
            "technical": 0.15,
            "quant": 0.1,
            "risk": 0.05,
        }
        effective = resolve_harness_mss_weights(
            state,
            base,
            settings={"harness": {"runtime_overlay_sources": ["memory"]}},
        )
        assert effective["fx"] > base["fx"]
        assert effective["technical"] < base["technical"]
        assert abs(sum(effective.values()) - 1.0) < 0.001

    def test_base_mss_defensive_trim_lowers_macro_baseline(self):
        state = HarnessState()
        state.entries["memory"]["miss"] = HarnessEntry(
            id="miss",
            kind="memory",
            title="盈亏目标未达",
            content="盈亏目标未达：目标 +100 实际 +0",
            source="deterministic",
            job="close",
            evidence="close",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        weights = resolve_harness_symbol_score_weights(
            state,
            settings={"harness": {"runtime_overlay_sources": ["memory"]}},
        )
        assert weights["base_mss"] == 45.0

    def test_kronos_playbook_parsing(self):
        state = HarnessState()
        state.entries["playbook"]["kronos_bull"] = HarnessEntry(
            id="kronos_bull",
            kind="playbook",
            title="Kronos 偏强",
            content="Kronos 偏强：京东方Ａ(000725) +4.6%、中际旭创(300308) +2.9%",
            source="deterministic",
            job="forecast",
            evidence="forecast",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        bullish, bearish = resolve_harness_kronos_bias(
            state,
            settings={"harness": {"runtime_overlay_sources": ["playbook"]}},
        )
        assert bullish["000725"] == 4.6
        assert bullish["300308"] == 2.9
        assert not bearish

    def test_kronos_score_adjustment(self):
        settings = {"harness_runtime": {"kronos_bullish": {"000725": 4.6}}}
        assert kronos_score_adjustment("000725", settings) > 0

    def test_symbol_score_prefers_kronos_bullish(self):
        settings = {"harness_runtime": {"kronos_bullish": {"300308": 3.0}}}
        bull = _symbol_score({"code": "300308", "change_pct": 0}, None, settings)
        plain = _symbol_score({"code": "603501", "change_pct": 0}, None, settings)
        assert bull > plain

    def test_symbol_score_weights_evolve_on_defensive_trim(self):
        state = HarnessState()
        state.entries["memory"]["miss"] = HarnessEntry(
            id="miss",
            kind="memory",
            title="MSS 预测偏离",
            content="MSS 预测偏离：下日调低进攻阈值或缩窄仓位",
            source="deterministic",
            job="close",
            evidence="close",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        settings = {"harness": {"runtime_overlay_sources": ["memory"]}}
        weights = resolve_harness_symbol_score_weights(state, settings=settings)
        assert weights["change_pct_weight"] == 0.25
        assert weights["position_20d_weight"] == 12.5

    def test_symbol_bias_from_harness_policy(self):
        state = HarnessState()
        state.entries["policy"]["deep_loss"] = HarnessEntry(
            id="deep_loss",
            kind="policy",
            title="深浮亏 海能达",
            content="深浮亏 002583：禁止接飞刀加仓，优先 verify 回避/减仓",
            source="deterministic",
            job="pnl_overview",
            evidence="pnl",
            created_at="2026-08-18T00:00:00+00:00",
            updated_at="2026-08-18T00:00:00+00:00",
        )
        bias = resolve_harness_symbol_bias(
            state,
            settings={"harness": {"runtime_overlay_sources": ["policy"]}},
        )
        assert bias["002583"] < 0

    def test_harness_symbol_score_applies_bias_and_change_weight(self):
        settings = {
            "harness_runtime": {
                "symbol_score_weights": {
                    "base_mss": 50.0,
                    "change_pct_weight": 0.25,
                    "position_20d_weight": 10.0,
                    "kronos_bullish_mult": 2.0,
                    "kronos_bearish_mult": 1.5,
                    "symbol_bias_penalty": 15.0,
                    "symbol_bias_boost": 8.0,
                },
                "symbol_bias": {"002583": -20.0},
            }
        }
        weak = harness_symbol_score({"code": "002583", "change_pct": 2.0}, settings)
        strong = harness_symbol_score({"code": "600584", "change_pct": 2.0}, settings)
        assert weak < strong

    def test_position_policy_evolve_on_defensive_trim(self):
        state = HarnessState()
        state.entries["memory"]["miss"] = HarnessEntry(
            id="miss",
            kind="memory",
            title="MSS 预测偏离",
            content="MSS 预测偏离：下日调低进攻阈值或缩窄仓位",
            source="deterministic",
            job="close",
            evidence="close",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        settings = {"harness": {"runtime_overlay_sources": ["memory"]}}
        policy = resolve_harness_position_policy(state, settings=settings)
        assert policy["deploy_ratio"] == 0.25
        assert policy["max_position_pct"] == 25.0

    def test_harness_buy_budget_caps_by_max_position_pct(self):
        settings = {
            "harness_runtime": {
                "position_policy": {"deploy_ratio": 1.0, "max_position_pct": 35.0},
            }
        }
        budget = harness_buy_budget(total=100_000, deployable=60_000, settings=settings)
        assert budget == 35_000

    def test_harness_buy_budget_scales_deploy_ratio(self):
        settings = {
            "harness_runtime": {
                "position_policy": {"deploy_ratio": 0.25, "max_position_pct": 35.0},
            }
        }
        budget = harness_buy_budget(total=100_000, deployable=60_000, settings=settings)
        assert budget == 15_000

    def test_defensive_trim_decision(self):
        settings = {
            "thresholds": {"macro_veto": 30, "aggressive_entry": 45, "min_cash_ratio": 0.5},
            "trading": {"commission_rate": 0.0015, "slippage_rate": 0.001, "holding_lock_days": 3},
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
            lookback_mss=54.0,
            trend="falling",
            verdict=verdict,
            report={"code": "688008", "name": "澜起科技", "blocked": False},
            snapshot={
                "portfolio": {
                    "cash_ratio": 0.75,
                    "holdings": [{"code": "688008", "days_held": 5}],
                }
            },
            settings=settings,
            trade_index=1,
            expected_return_pct=0.01,
        )
        assert decision.action == "sell"
        assert "防御性减仓" in decision.reasoning

    def test_defensive_trim_hold_when_decision_symbol_not_sellable(self):
        settings = {
            "thresholds": {"macro_veto": 30, "aggressive_entry": 45, "min_cash_ratio": 0.5},
            "trading": {"commission_rate": 0.0015, "slippage_rate": 0.001, "holding_lock_days": 3},
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
            lookback_mss=54.0,
            trend="falling",
            verdict=verdict,
            report={"code": "688008", "name": "澜起科技", "blocked": False},
            snapshot={
                "portfolio": {
                    "cash_ratio": 0.75,
                    "holdings": [
                        {"code": "688008", "days_held": 0},
                        {"code": "002583", "days_held": 5},
                    ],
                }
            },
            settings=settings,
            trade_index=1,
            expected_return_pct=0.01,
        )
        assert decision.action == "hold"
        assert "防御性减仓" not in decision.reasoning

    def test_defensive_trim_hold_when_deep_loss_not_covered(self, tmp_path, monkeypatch):
        ledger = tmp_path / "trade_ledger.jsonl"
        ledger.write_text("", encoding="utf-8")
        monkeypatch.setattr("agent_reach.daily_run.realized_pnl.default_ledger_path", lambda: ledger)

        settings = {
            "thresholds": {"macro_veto": 30, "aggressive_entry": 45, "min_cash_ratio": 0.5},
            "trading": {"commission_rate": 0.0015, "slippage_rate": 0.001, "holding_lock_days": 1},
            "pnl_overview": {"deep_loss_sell_require_cover": True, "large_unrealized_loss_cny": 5000},
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
            lookback_mss=54.0,
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
            trade_index=1,
            expected_return_pct=0.01,
        )
        assert decision.action == "hold"
        assert "深度套牢" in decision.reasoning
        assert "不足" in decision.reasoning

    def test_deep_loss_policy_evolve_on_defensive_trim(self):
        from agent_reach.daily_run.harness import HarnessState
        from agent_reach.daily_run.harness_policy import resolve_harness_deep_loss_policy

        state = HarnessState()
        settings = {"harness": {"runtime_overlay_sources": ["memory"]}}
        base = resolve_harness_deep_loss_policy(state, settings=settings)
        assert base["sell_ratio"] == 1.0

        state.entries["memory"]["miss"] = HarnessEntry(
            id="miss",
            kind="memory",
            title="MSS 预测偏离",
            content="MSS 预测偏离：下日调低进攻阈值或缩窄仓位",
            source="deterministic",
            job="close",
            evidence="close",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        from agent_reach.daily_run.harness_policy import resolve_harness_trade_signals

        signals = resolve_harness_trade_signals(state, settings=settings)
        assert signals.get("defensive_trim")
        policy = resolve_harness_deep_loss_policy(state, settings=settings)
        assert policy["sell_ratio"] == 0.5
        assert policy["cover_ratio"] >= 1.0

    def test_deep_loss_policy_from_pnl_harness_phrase(self):
        from agent_reach.daily_run.harness import HarnessEntry, HarnessState
        from agent_reach.daily_run.harness_policy import resolve_harness_deep_loss_policy

        state = HarnessState()
        state.entries["policy"]["trap"] = HarnessEntry(
            id="trap",
            kind="policy",
            title="深度套牢 海能达",
            content="深度套牢 002583：cover_ratio≥1.0，sell_ratio≤0.5，卖出前需组合盈利覆盖浮亏",
            source="deterministic",
            job="pnl_overview",
            evidence="pnl",
            created_at="2026-08-18T00:00:00+00:00",
            updated_at="2026-08-18T00:00:00+00:00",
        )
        policy = resolve_harness_deep_loss_policy(
            state,
            settings={"harness": {"runtime_overlay_sources": ["policy"]}},
        )
        assert policy["loss_cny_threshold"] <= 4000
        assert policy["sell_ratio"] <= 0.5

    def test_deep_loss_realized_loss_phrase_tightens_cover(self):
        from agent_reach.daily_run.harness import HarnessEntry, HarnessState
        from agent_reach.daily_run.harness_policy import resolve_harness_deep_loss_policy

        state = HarnessState()
        state.entries["policy"]["realized"] = HarnessEntry(
            id="realized",
            kind="policy",
            title="已实现亏损较大",
            content="已实现亏损较大：澜起科技 卖出后复盘入场/止损纪律",
            source="deterministic",
            job="pnl_overview",
            evidence="pnl",
            created_at="2026-08-18T00:00:00+00:00",
            updated_at="2026-08-18T00:00:00+00:00",
        )
        policy = resolve_harness_deep_loss_policy(
            state,
            settings={"harness": {"runtime_overlay_sources": ["policy"]}},
        )
        assert policy["cover_ratio"] >= 1.05
        assert policy["realized_loss_threshold"] <= 400

    def test_portfolio_loss_phrase_tightens_position_policy(self):
        from agent_reach.daily_run.harness import HarnessEntry, HarnessState
        from agent_reach.daily_run.harness_policy import (
            resolve_harness_deep_loss_policy,
            resolve_harness_position_policy,
        )

        state = HarnessState()
        state.entries["policy"]["pf_loss"] = HarnessEntry(
            id="pf_loss",
            kind="policy",
            title="组合浮亏",
            content="浮动亏损主导净值：维持高现金，减少新开仓",
            source="deterministic",
            job="pnl_overview",
            evidence="pnl",
            created_at="2026-08-18T00:00:00+00:00",
            updated_at="2026-08-18T00:00:00+00:00",
        )
        settings = {"harness": {"runtime_overlay_sources": ["policy"]}}
        pos = resolve_harness_position_policy(state, settings=settings)
        deep = resolve_harness_deep_loss_policy(state, settings=settings)
        assert pos["deploy_ratio"] <= 0.25
        assert deep["portfolio_loss_cny_threshold"] <= 4000

    def test_win_rate_phrase_evolves_deep_loss_and_position(self):
        from agent_reach.daily_run.harness import HarnessEntry, HarnessState
        from agent_reach.daily_run.harness_policy import (
            resolve_harness_deep_loss_policy,
            resolve_harness_position_policy,
        )

        state = HarnessState()
        state.entries["policy"]["winrate"] = HarnessEntry(
            id="winrate",
            kind="policy",
            title="卖出胜率",
            content="卖出胜率偏低：1盈/4亏（<33%）",
            source="deterministic",
            job="pnl_overview",
            evidence="pnl",
            created_at="2026-08-18T00:00:00+00:00",
            updated_at="2026-08-18T00:00:00+00:00",
        )
        settings = {"harness": {"runtime_overlay_sources": ["policy"]}}
        deep = resolve_harness_deep_loss_policy(state, settings=settings)
        pos = resolve_harness_position_policy(state, settings=settings)
        assert deep["cover_ratio"] >= 1.1
        assert deep["coverable_realized_weight"] <= 0.75
        assert pos["deploy_ratio"] <= 0.35

    def test_loss_streak_phrase_evolves_policy(self):
        from agent_reach.daily_run.harness import HarnessEntry, HarnessState
        from agent_reach.daily_run.harness_policy import resolve_harness_deep_loss_policy

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
        policy = resolve_harness_deep_loss_policy(
            state,
            settings={"harness": {"runtime_overlay_sources": ["policy"]}},
        )
        assert policy["cover_ratio"] >= 1.15
        assert policy["sell_ratio"] <= 0.4

    def test_rejected_blocks_buy(self, tmp_path, monkeypatch):
        rej = tmp_path / "rejected_strategies.jsonl"
        monkeypatch.setattr("agent_reach.daily_run.skill_rejected._REJECTED_PATH", rej)
        add_rejected_strategy("禁止接飞刀追涨", "宏观回避期逆势加仓已证伪")
        blocked = trade_blocked_by_rejected("buy", name="中际旭创", settings={"harness": {}})
        assert blocked

    def test_trade_signals_from_memory(self):
        state = HarnessState()
        state.entries["memory"]["miss"] = HarnessEntry(
            id="miss",
            kind="memory",
            title="MSS 预测偏离",
            content="MSS 预测偏离：下日调低进攻阈值或缩窄仓位",
            source="deterministic",
            job="close",
            evidence="close",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        signals = resolve_harness_trade_signals(
            state,
            settings={"harness": {"runtime_overlay_sources": ["memory"]}},
        )
        assert signals["mss_forecast_miss"] is True
        assert signals["defensive_trim"] is True

    def test_pnl_target_miss_triggers_defensive_signals(self):
        state = HarnessState()
        state.entries["memory"]["pnl_miss"] = HarnessEntry(
            id="pnl_miss",
            kind="memory",
            title="pnl_target",
            content="盈亏目标未达：目标 +500 实际 -200（差 -700）",
            source="deterministic",
            job="pnl_target",
            evidence="pnl_target miss",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        signals = resolve_harness_trade_signals(
            state,
            settings={"harness": {"runtime_overlay_sources": ["memory"]}},
        )
        assert signals["pnl_target_miss"] is True
        assert signals["defensive_trim"] is True

    def test_pnl_target_hit_relaxes_aggressive_entry(self):
        state = HarnessState()
        state.entries["memory"]["pnl_hit"] = HarnessEntry(
            id="pnl_hit",
            kind="memory",
            title="pnl_target",
            content="盈亏目标达成：目标 +500 实际 +800",
            source="deterministic",
            job="pnl_target",
            evidence="pnl_target hit",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        flat = resolve_harness_flat_overrides(
            state,
            {"macro_veto": 40, "aggressive_entry": 50, "min_cash_ratio": 0.3},
            settings=_harness_settings(),
        )
        assert flat["aggressive_entry"] >= 52.0

    def test_pnl_target_policy_evolution_on_miss(self):
        from agent_reach.daily_run.harness import HarnessEntry, HarnessState
        from agent_reach.daily_run.harness_policy import resolve_harness_pnl_target_policy

        state = HarnessState()
        state.entries["memory"]["pnl_miss"] = HarnessEntry(
            id="pnl_miss",
            kind="memory",
            title="pnl_target",
            content="盈亏目标未达：目标 +500 实际 -200（差 -700）",
            source="deterministic",
            job="pnl_target",
            evidence="pnl_target miss",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        policy = resolve_harness_pnl_target_policy(
            state,
            settings={
                "harness": {"runtime_overlay_sources": ["memory"]},
                "pnl_target": {"base_target_pct": 0.5, "min_target_cny": 100},
            },
        )
        assert policy["base_target_pct"] <= 0.4
        assert policy["min_target_cny"] <= 80

    def test_bad_trade_policy_evolution_on_miss(self):
        from agent_reach.daily_run.harness_policy import (
            bad_trade_policy_default,
            resolve_harness_bad_trade_policy,
        )

        state = HarnessState()
        state.entries["memory"]["pnl_miss"] = HarnessEntry(
            id="pnl_miss",
            kind="memory",
            title="pnl_target",
            content="盈亏目标未达：目标 +500 实际 -200（差 -700）",
            source="deterministic",
            job="pnl_target",
            evidence="pnl_target miss",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        settings = {
            "harness": {
                "runtime_overlay_sources": ["memory"],
                "bad_trade_pnl_pct_mode": "harness",
                "bad_trade_weekly_pnl_pct_mode": "harness",
            },
        }
        policy = resolve_harness_bad_trade_policy(state, settings=settings)
        assert policy["bad_trade_pnl_pct"] == -0.8
        assert policy["bad_trade_weekly_pnl_pct"] == -1.5
        eff = apply_harness_policy_overlay({**settings, "thresholds": {}})
        assert eff["harness"]["bad_trade_pnl_pct"] == -0.8
        assert bad_trade_policy_default(eff, "bad_trade_pnl_pct") == -0.8

    def test_realized_gain_threshold_separate_from_loss(self):
        from agent_reach.daily_run.harness_policy import deep_loss_policy_base

        settings = {
            "pnl_overview": {
                "large_realized_loss_cny": 500,
                "large_realized_gain_cny": 800,
            }
        }
        assert deep_loss_policy_base(settings, "realized_loss_threshold") == 500
        assert deep_loss_policy_base(settings, "realized_gain_threshold") == 800


class TestHarnessP2Evolution:
    def test_harness_mode_technical_neutral_defaults(self):
        state = HarnessState()
        flat = resolve_harness_flat_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=_harness_settings(),
        )
        assert flat["high_position_20d"] == 0.7
        assert flat["min_volume_ratio"] == 1.0
        assert flat["max_vwap_deviation_pct"] == 0.04
        assert flat["base_spread"] == 8.0
        assert flat["vol_multiplier"] == 6.0
        assert flat["friction_min_return_pct"] == 0.005

    def test_defensive_technical_evolution(self):
        state = HarnessState()
        state.entries["memory"]["dev"] = HarnessEntry(
            id="dev",
            kind="memory",
            title="偏差",
            content="偏差：价格变动 23.7% 超过锚点阈值 8.0%",
            source="deterministic",
            job="forecast",
            evidence="forecast",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        flat = resolve_harness_flat_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=_harness_settings(),
        )
        assert flat["high_position_20d"] == 0.65
        assert flat["min_volume_ratio"] == 1.1
        assert flat["max_vwap_deviation_pct"] == 0.03
        assert flat["friction_min_return_pct"] == 0.008
        assert flat["base_spread"] == 10.0
        assert flat["vol_multiplier"] == 7.0

    def test_offensive_technical_memory(self):
        state = HarnessState()
        state.entries["memory"]["offense"] = HarnessEntry(
            id="offense",
            kind="memory",
            title="宏观回暖",
            content="宏观回暖：北向回流改善，降低现金比例",
            source="deterministic",
            job="weekly",
            evidence="weekly",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        flat = resolve_harness_flat_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=_harness_settings(),
        )
        assert flat["high_position_20d"] == 0.75
        assert flat["min_volume_ratio"] == 1.0
        assert flat["max_vwap_deviation_pct"] == 0.05
        assert flat["friction_min_return_pct"] == 0.004

    def test_forecast_int_default_before_overlay(self):
        settings = _harness_settings()
        assert forecast_int_default(settings, "base_spread") == 8
        assert forecast_int_default(settings, "vol_multiplier") == 6

    def test_friction_gate_uses_evolved_threshold(self):
        settings = _harness_settings()
        assert friction_min_return_default(settings) == 0.005
        assert _passes_friction(0.006, settings) is True
        assert _passes_friction(0.004, settings) is False

    def test_effective_settings_applies_forecast_and_friction(self, monkeypatch):
        state = HarnessState()
        state.entries["memory"]["dev"] = HarnessEntry(
            id="dev",
            kind="memory",
            title="偏差",
            content="偏差：价格变动 23.7% 超过锚点阈值 8.0%",
            source="deterministic",
            job="forecast",
            evidence="forecast",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.harness.load_harness",
            lambda: state,
        )
        cfg = effective_settings(_harness_settings())
        assert cfg["mss_forecast"]["base_spread"] == 10
        assert cfg["mss_forecast"]["vol_multiplier"] == 7
        assert cfg["trading"]["friction_min_return_pct"] == 0.008
        assert cfg["thresholds"]["high_position_20d"] == 0.65
        assert "forecast_overlay" in cfg.get("harness_runtime", {})

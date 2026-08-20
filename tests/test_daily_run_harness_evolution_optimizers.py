# -*- coding: utf-8
"""Tests for DeepSeek harness threshold / pnl_target / forecast optimizers."""

from unittest.mock import patch

from agent_reach.daily_run.harness import HarnessEntry, HarnessState
from agent_reach.daily_run.harness_evolution_optimizers import (
    apply_forecast_llm_optimal_to_flat,
    apply_pnl_target_llm_optimal_to_policy,
    apply_threshold_llm_optimal_to_flat,
    format_forecast_policy_line,
    format_pnl_target_policy_line,
    format_threshold_policy_line,
    optimize_forecast_calibrate_with_deepseek,
    optimize_pnl_target_with_deepseek,
    optimize_weekly_threshold_with_deepseek,
    parse_forecast_policy_line,
    parse_pnl_target_policy_line,
    parse_threshold_policy_line,
)
from agent_reach.daily_run.harness_policy import (
    resolve_harness_flat_overrides,
    resolve_harness_pnl_target_policy,
)


class TestHarnessEvolutionOptimizerHelpers:
    def test_parse_threshold_policy_line(self):
        line = format_threshold_policy_line(
            {
                "macro_veto": 42.0,
                "aggressive_entry": 52.0,
                "min_cash_ratio": 0.35,
                "friction_min_return_pct": 0.006,
                "trend_min_points": 3.0,
            },
            rationale="test",
        )
        parsed = parse_threshold_policy_line(line)
        assert parsed["macro_veto"] == 42.0
        assert parsed["aggressive_entry"] == 52.0
        assert parsed["min_cash_ratio"] == 0.35
        assert parsed["friction_min_return_pct"] == 0.006
        assert parsed["trend_min_points"] == 3.0

    def test_parse_pnl_target_policy_line(self):
        line = format_pnl_target_policy_line(
            {
                "base_target_pct": 0.55,
                "streak_bonus_pct": 12.0,
                "miss_recovery_factor": 0.85,
            }
        )
        parsed = parse_pnl_target_policy_line(line)
        assert parsed["base_target_pct"] == 0.55
        assert parsed["streak_bonus_pct"] == 12.0
        assert parsed["miss_recovery_factor"] == 0.85

    def test_parse_forecast_policy_line(self):
        line = format_forecast_policy_line({"base_spread": 9.0, "vol_multiplier": 6.5})
        parsed = parse_forecast_policy_line(line)
        assert parsed["base_spread"] == 9.0
        assert parsed["vol_multiplier"] == 6.5


class TestHarnessEvolutionDeepSeekOptimize:
    @patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value="deepseek")
    @patch("agent_reach.daily_run.llm_chat.chat_json")
    def test_optimize_weekly_threshold_returns_evidence(self, mock_chat, _provider):
        mock_chat.return_value = {
            "macro_veto": 43.0,
            "aggressive_entry": 53.0,
            "min_cash_ratio": 0.4,
            "friction_min_return_pct": 0.006,
            "trend_min_points": 3,
            "rationale": "周度偏防御",
            "confidence": 0.8,
        }
        report = {
            "week_start": "2026-08-18",
            "week_end": "2026-08-22",
            "weekly_pnl": -500.0,
            "sell_rules_whatif": {"realized_pnl_delta": -200.0, "skipped": False},
            "buy_rules_whatif": {"buy_notional_delta": -1000.0, "skipped": False},
        }
        result = optimize_weekly_threshold_with_deepseek(report, settings={"harness_evolution": {}})
        assert not result["skipped"]
        assert result["optimal"]["macro_veto"] == 43.0
        assert any("阈值最优" in line for line in result["evidence"]["policy"])

    @patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value="deepseek")
    @patch("agent_reach.daily_run.llm_chat.chat_json")
    def test_optimize_pnl_target_returns_evidence(self, mock_chat, _provider):
        mock_chat.return_value = {
            "base_target_pct": 0.55,
            "streak_bonus_pct": 12.0,
            "miss_recovery_factor": 0.85,
            "rationale": "hit 后略升目标",
            "confidence": 0.75,
        }
        cycle = {
            "evaluated": {"hit": True, "target_pnl_cny": 100.0, "actual_pnl_cny": 120.0},
            "next_target": {"target_date": "2026-08-20", "target_pnl_cny": 110.0},
        }
        result = optimize_pnl_target_with_deepseek(cycle, settings={"harness_evolution": {}})
        assert not result["skipped"]
        assert result["optimal"]["base_target_pct"] == 0.55
        assert any("pnl_target最优" in line for line in result["evidence"]["policy"])

    @patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value="deepseek")
    @patch("agent_reach.daily_run.llm_chat.chat_json")
    def test_optimize_forecast_returns_evidence(self, mock_chat, _provider):
        mock_chat.return_value = {
            "base_spread": 9.0,
            "vol_multiplier": 6.5,
            "rationale": "分歧日偏多",
            "confidence": 0.7,
        }
        forecast = {
            "week_start": "2026-08-18",
            "week_end": "2026-08-22",
            "calibration_used": {"vol_scale": 1.1},
            "symbols": {"000001": {"kronos_divergence_days": ["2026-08-19"]}},
            "notes": ["MSS 预测偏离"],
        }
        result = optimize_forecast_calibrate_with_deepseek(forecast, settings={"harness_evolution": {}})
        assert not result["skipped"]
        assert result["optimal"]["base_spread"] == 9.0
        assert any("forecast最优" in line for line in result["evidence"]["policy"])

    @patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None)
    def test_skips_without_api_key(self, _provider):
        result = optimize_weekly_threshold_with_deepseek(
            {"sell_rules_whatif": {}, "buy_rules_whatif": {}},
            settings={"harness_evolution": {}},
        )
        assert result["skipped"] is True


class TestHarnessEvolutionLlmOptimalOverlay:
    def _settings(self) -> dict:
        return {
            "thresholds": {"max_snapshot_age_hours": 24},
            "harness": {
                "enabled": True,
                "runtime_overlay": True,
                "threshold_evolution_mode": "harness",
                "macro_veto_mode": "harness",
                "aggressive_entry_mode": "harness",
                "min_cash_ratio_mode": "harness",
                "base_spread_mode": "harness",
                "vol_multiplier_mode": "harness",
                "base_target_pct_mode": "harness",
                "streak_bonus_pct_mode": "harness",
                "miss_recovery_factor_mode": "harness",
                "runtime_overlay_sources": ["policy"],
            },
        }

    def test_threshold_llm_optimal_overrides_flat(self):
        state = HarnessState()
        line = format_threshold_policy_line(
            {
                "macro_veto": 43.0,
                "aggressive_entry": 53.0,
                "min_cash_ratio": 0.4,
                "friction_min_return_pct": 0.006,
                "trend_min_points": 3.0,
            }
        )
        state.entries["policy"]["llm_threshold"] = HarnessEntry(
            id="llm_threshold",
            kind="policy",
            title="llm threshold",
            content=line,
            source="llm",
            job="harness_threshold",
            evidence="weekly",
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        )
        flat = resolve_harness_flat_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=self._settings(),
        )
        assert flat["macro_veto"] == 43.0
        assert flat["aggressive_entry"] == 53.0
        assert flat["min_cash_ratio"] == 0.4
        assert flat["friction_min_return_pct"] == 0.006
        assert flat["trend_min_points"] == 3.0

    def test_forecast_llm_optimal_overrides_flat(self):
        state = HarnessState()
        line = format_forecast_policy_line({"base_spread": 9.0, "vol_multiplier": 7.0})
        state.entries["policy"]["llm_forecast"] = HarnessEntry(
            id="llm_forecast",
            kind="policy",
            title="llm forecast",
            content=line,
            source="llm",
            job="forecast_calibrate",
            evidence="forecast",
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        )
        flat = resolve_harness_flat_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=self._settings(),
        )
        assert flat["base_spread"] == 9.0
        assert flat["vol_multiplier"] == 7.0

    def test_pnl_target_llm_optimal_overrides_policy(self):
        state = HarnessState()
        line = format_pnl_target_policy_line(
            {
                "base_target_pct": 0.55,
                "streak_bonus_pct": 12.0,
                "miss_recovery_factor": 0.85,
            }
        )
        state.entries["policy"]["llm_pnl"] = HarnessEntry(
            id="llm_pnl",
            kind="policy",
            title="llm pnl",
            content=line,
            source="llm",
            job="pnl_target",
            evidence="close",
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        )
        policy = resolve_harness_pnl_target_policy(state, settings=self._settings())
        assert policy["base_target_pct"] == 0.55
        assert policy["streak_bonus_pct"] == 12.0
        assert policy["miss_recovery_factor"] == 0.85

    def test_apply_helpers_on_merged_dict(self):
        state = HarnessState()
        threshold_line = format_threshold_policy_line(
            {"macro_veto": 44.0, "aggressive_entry": 54.0, "min_cash_ratio": 0.42}
        )
        forecast_line = format_forecast_policy_line({"base_spread": 10.0, "vol_multiplier": 7.0})
        pnl_line = format_pnl_target_policy_line(
            {"base_target_pct": 0.52, "streak_bonus_pct": 11.0, "miss_recovery_factor": 0.82}
        )
        state.entries["policy"]["t"] = HarnessEntry(
            id="t",
            kind="policy",
            title="t",
            content=threshold_line,
            source="llm",
            job="harness_threshold",
            evidence="weekly",
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        )
        state.entries["policy"]["f"] = HarnessEntry(
            id="f",
            kind="policy",
            title="f",
            content=forecast_line,
            source="llm",
            job="forecast_calibrate",
            evidence="forecast",
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        )
        state.entries["policy"]["p"] = HarnessEntry(
            id="p",
            kind="policy",
            title="p",
            content=pnl_line,
            source="llm",
            job="pnl_target",
            evidence="close",
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        )
        settings = self._settings()
        flat = {"macro_veto": 40.0, "aggressive_entry": 50.0, "min_cash_ratio": 0.0}
        assert apply_threshold_llm_optimal_to_flat(flat, state, settings=settings) is True
        assert flat["macro_veto"] == 44.0

        flat2 = {"base_spread": 8.0, "vol_multiplier": 6.0}
        assert apply_forecast_llm_optimal_to_flat(flat2, state, settings=settings) is True
        assert flat2["base_spread"] == 10.0

        pnl = {"base_target_pct": 0.5, "streak_bonus_pct": 10.0, "miss_recovery_factor": 0.8}
        assert apply_pnl_target_llm_optimal_to_policy(pnl, state, settings=settings) is True
        assert pnl["base_target_pct"] == 0.52

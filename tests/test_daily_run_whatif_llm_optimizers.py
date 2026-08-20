# -*- coding: utf-8
"""Tests for intraday sell / sell threshold / intraday trends DeepSeek optimizers."""

from unittest.mock import patch

from agent_reach.daily_run.harness import HarnessEntry, HarnessState
from agent_reach.daily_run.harness_policy import (
    resolve_harness_deep_loss_policy,
    resolve_harness_flat_overrides,
    resolve_harness_trend_policy,
)
from agent_reach.daily_run.intraday_sell_whatif_optimizer import (
    apply_intraday_sell_llm_optimal_to_deep_loss,
    apply_intraday_sell_llm_optimal_to_flat,
    format_intraday_sell_policy_line,
    optimize_intraday_sell_with_deepseek,
    parse_intraday_sell_policy_line,
)
from agent_reach.daily_run.intraday_trends_optimizer import (
    apply_intraday_trends_llm_optimal_to_trend,
    format_intraday_trends_policy_line,
    optimize_intraday_trends_with_deepseek,
    parse_intraday_trends_policy_line,
)
from agent_reach.daily_run.sell_threshold_optimizer import (
    apply_sell_threshold_llm_optimal_to_flat,
    format_sell_threshold_policy_line,
    optimize_sell_threshold_with_deepseek,
    parse_sell_threshold_policy_line,
)


class TestIntradaySellWhatIfOptimizer:
    def test_parse_policy_line(self):
        line = format_intraday_sell_policy_line(
            {"sell_ratio": 0.65, "non_deep_loss_sell_ratio": 0.7, "macro_veto": 36.0}
        )
        parsed = parse_intraday_sell_policy_line(line)
        assert parsed["sell_ratio"] == 0.65
        assert parsed["macro_veto"] == 36.0

    @patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value="deepseek")
    @patch("agent_reach.daily_run.llm_chat.chat_json")
    def test_optimize_returns_evidence(self, mock_chat, _provider):
        mock_chat.return_value = {
            "sell_ratio": 0.65,
            "non_deep_loss_sell_ratio": 0.7,
            "macro_veto": 36,
            "rationale": "scan 错失偏多",
            "confidence": 0.7,
        }
        source = {
            "as_of": "2026-08-19",
            "intraday_sell_whatif": {
                "skipped": False,
                "missed_sell_signals": 2,
                "sell_share_delta": 700,
                "rows": [],
            },
        }
        result = optimize_intraday_sell_with_deepseek(source, settings={"intraday_sell_whatif": {}})
        assert not result["skipped"]
        assert any("卖出scan最优" in line for line in result["evidence"]["policy"])

    def test_llm_optimal_overrides_runtime(self):
        state = HarnessState()
        line = format_intraday_sell_policy_line(
            {"sell_ratio": 0.65, "non_deep_loss_sell_ratio": 0.7, "macro_veto": 36.0}
        )
        state.entries["policy"]["llm_sell_scan"] = HarnessEntry(
            id="llm_sell_scan",
            kind="policy",
            title="llm sell scan",
            content=line,
            source="llm",
            job="intraday_sell",
            evidence="close",
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        )
        settings = {
            "thresholds": {"macro_veto": 40, "aggressive_entry": 50},
            "harness": {
                "enabled": True,
                "runtime_overlay": True,
                "threshold_evolution_mode": "harness",
                "sell_ratio_mode": "harness",
                "non_deep_loss_sell_ratio_mode": "harness",
                "macro_veto_mode": "harness",
                "runtime_overlay_sources": ["policy"],
            },
        }
        flat = resolve_harness_flat_overrides(
            state,
            {"macro_veto": 40, "aggressive_entry": 50},
            settings=settings,
        )
        assert flat["macro_veto"] == 36.0
        deep_loss = resolve_harness_deep_loss_policy(state, settings=settings)
        assert deep_loss["sell_ratio"] == 0.65
        assert deep_loss["non_deep_loss_sell_ratio"] == 0.7

        merged_flat = {"macro_veto": 40.0}
        assert apply_intraday_sell_llm_optimal_to_flat(merged_flat, state, settings=settings)
        assert merged_flat["macro_veto"] == 36.0
        merged_dl = {"sell_ratio": 0.5, "non_deep_loss_sell_ratio": 0.5}
        assert apply_intraday_sell_llm_optimal_to_deep_loss(merged_dl, state, settings=settings)
        assert merged_dl["sell_ratio"] == 0.65


class TestSellThresholdOptimizer:
    def test_parse_policy_line(self):
        line = format_sell_threshold_policy_line(
            {"macro_veto": 36.0, "aggressive_entry": 50.0}
        )
        parsed = parse_sell_threshold_policy_line(line)
        assert parsed["macro_veto"] == 36.0
        assert parsed["aggressive_entry"] == 50.0

    @patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value="deepseek")
    @patch("agent_reach.daily_run.llm_chat.chat_json")
    def test_optimize_returns_evidence(self, mock_chat, _provider):
        mock_chat.return_value = {
            "macro_veto": 36,
            "aggressive_entry": 50,
            "rationale": "scan 错失",
            "confidence": 0.7,
        }
        report = {
            "week_start": "2026-08-18",
            "week_end": "2026-08-22",
            "sell_rules_whatif": {"skipped": False, "realized_pnl_delta": -500},
            "intraday_sell_whatif": {"skipped": False, "missed_sell_signals": 2},
        }
        result = optimize_sell_threshold_with_deepseek(report, settings={"sell_threshold": {}})
        assert not result["skipped"]
        assert any("卖出阈值最优" in line for line in result["evidence"]["policy"])

    def test_llm_optimal_overrides_flat(self):
        state = HarnessState()
        line = format_sell_threshold_policy_line(
            {"macro_veto": 36.0, "aggressive_entry": 51.0}
        )
        state.entries["policy"]["llm_sell_threshold"] = HarnessEntry(
            id="llm_sell_threshold",
            kind="policy",
            title="llm sell threshold",
            content=line,
            source="llm",
            job="sell_rules_whatif",
            evidence="weekly",
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        )
        settings = {
            "thresholds": {"macro_veto": 40, "aggressive_entry": 50},
            "harness": {
                "enabled": True,
                "runtime_overlay": True,
                "threshold_evolution_mode": "harness",
                "runtime_overlay_sources": ["policy"],
            },
        }
        merged = {"macro_veto": 40.0, "aggressive_entry": 50.0}
        assert apply_sell_threshold_llm_optimal_to_flat(merged, state, settings=settings)
        assert merged["macro_veto"] == 36.0
        assert merged["aggressive_entry"] == 51.0


class TestIntradayTrendsOptimizer:
    def test_parse_policy_line(self):
        line = format_intraday_trends_policy_line(
            {
                "buy_trends": ["rising", "turning_up"],
                "sell_trends": ["falling", "turning_down", "mixed"],
            }
        )
        parsed = parse_intraday_trends_policy_line(line)
        assert parsed["buy_trends"] == ["rising", "turning_up"]
        assert "mixed" in parsed["sell_trends"]

    @patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value="deepseek")
    @patch("agent_reach.daily_run.llm_chat.chat_json")
    def test_optimize_returns_evidence(self, mock_chat, _provider):
        mock_chat.return_value = {
            "buy_trends": ["rising"],
            "sell_trends": ["falling", "turning_down", "mixed"],
            "rationale": "趋势误判",
            "confidence": 0.7,
        }
        source = {
            "as_of": "2026-08-19",
            "intraday_friction_whatif": {
                "skipped": False,
                "trend_mismatch": 2,
                "friction_would_pass": 0,
                "rows": [],
            },
        }
        result = optimize_intraday_trends_with_deepseek(source, settings={"intraday_trends": {}})
        assert not result["skipped"]
        assert any("趋势集合最优" in line for line in result["evidence"]["policy"])

    def test_llm_optimal_overrides_trend_policy(self):
        state = HarnessState()
        line = format_intraday_trends_policy_line(
            {
                "buy_trends": ["rising"],
                "sell_trends": ["falling", "mixed", "flat"],
            }
        )
        state.entries["policy"]["llm_trends"] = HarnessEntry(
            id="llm_trends",
            kind="policy",
            title="llm trends",
            content=line,
            source="llm",
            job="intraday_friction",
            evidence="close",
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        )
        settings = {
            "intraday": {
                "buy_trends": ["rising", "turning_up"],
                "sell_trends": ["falling", "turning_down"],
            },
            "harness": {
                "enabled": True,
                "runtime_overlay": True,
                "threshold_evolution_mode": "harness",
                "runtime_overlay_sources": ["policy"],
            },
        }
        trend = resolve_harness_trend_policy(state, settings=settings)
        assert trend["buy_trends"] == ["rising"]
        assert "mixed" in trend["sell_trends"]

        trend_m = {"buy_trends": ["rising", "turning_up"], "sell_trends": ["falling"]}
        assert apply_intraday_trends_llm_optimal_to_trend(trend_m, state, settings=settings)
        assert trend_m["buy_trends"] == ["rising"]
        assert "flat" in trend_m["sell_trends"]

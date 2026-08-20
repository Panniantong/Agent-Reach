# -*- coding: utf-8
"""Tests for DeepSeek buy what-if optimizer."""

from unittest.mock import patch

from agent_reach.daily_run.harness import HarnessEntry, HarnessState
from agent_reach.daily_run.harness_policy import resolve_harness_position_policy
from agent_reach.daily_run.buy_rules_whatif_optimizer import (
    apply_whatif_buy_llm_optimal_to_policy,
    clamp_buy_optimal,
    format_buy_llm_optimal_policy_line,
    optimize_buy_rules_whatif_with_deepseek,
    parse_buy_llm_optimal_policy_line,
)


class TestBuyWhatIfOptimizerHelpers:
    def test_clamp_buy_bounds(self):
        ratios = clamp_buy_optimal({"deploy_ratio": 1.5, "max_position_pct": 80.0})
        assert ratios["deploy_ratio"] == 1.0
        assert ratios["max_position_pct"] == 50.0

    def test_parse_buy_policy_line(self):
        line = format_buy_llm_optimal_policy_line(
            {"deploy_ratio": 0.55, "max_position_pct": 28.0},
            rationale="test",
        )
        parsed = parse_buy_llm_optimal_policy_line(line)
        assert parsed["deploy_ratio"] == 0.55
        assert parsed["max_position_pct"] == 28.0


class TestBuyWhatIfDeepSeekOptimize:
    @patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value="deepseek")
    @patch("agent_reach.daily_run.llm_chat.chat_json")
    def test_optimize_returns_evidence(self, mock_chat, _provider):
        mock_chat.return_value = {
            "deploy_ratio": 0.62,
            "max_position_pct": 32.0,
            "rationale": "基准买入更积极，适度上调 deploy",
            "confidence": 0.78,
        }
        report = {
            "week_start": "2026-08-18",
            "week_end": "2026-08-22",
            "weekly_pnl": 800.0,
            "buy_rules_whatif": {
                "skipped": False,
                "actual_buy_notional": 12000.0,
                "hypothetical_buy_notional": 7000.0,
                "buy_notional_delta": -5000.0,
                "rows": [],
            },
        }
        result = optimize_buy_rules_whatif_with_deepseek(report, settings={"buy_rules_whatif": {}})
        assert not result["skipped"]
        assert result["optimal"]["deploy_ratio"] == 0.62
        assert any("买入最优" in line for line in result["evidence"]["policy"])

    @patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None)
    def test_skips_without_api_key(self, _provider):
        result = optimize_buy_rules_whatif_with_deepseek(
            {"buy_rules_whatif": {"skipped": False, "rows": []}},
            settings={"buy_rules_whatif": {}},
        )
        assert result["skipped"] is True


class TestBuyWhatIfLlmOptimalOverlay:
    def test_llm_optimal_overrides_position_policy(self):
        state = HarnessState()
        line = format_buy_llm_optimal_policy_line(
            {"deploy_ratio": 0.62, "max_position_pct": 32.0}
        )
        state.entries["policy"]["llm_buy"] = HarnessEntry(
            id="llm_buy",
            kind="policy",
            title="llm buy optimal",
            content=line,
            source="llm",
            job="sell_rules_whatif",
            evidence="weekly",
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        )
        settings = {
            "harness": {
                "runtime_overlay_sources": ["policy"],
                "deploy_ratio_mode": "harness",
                "max_position_pct_mode": "harness",
            },
        }
        policy = resolve_harness_position_policy(state, settings=settings)
        assert policy["deploy_ratio"] == 0.62
        assert policy["max_position_pct"] == 32.0

    def test_apply_to_merged_dict(self):
        state = HarnessState()
        line = format_buy_llm_optimal_policy_line(
            {"deploy_ratio": 0.6, "max_position_pct": 30.0}
        )
        state.entries["policy"]["llm_buy"] = HarnessEntry(
            id="llm_buy",
            kind="policy",
            title="llm",
            content=line,
            source="llm",
            job="sell_rules_whatif",
            evidence="weekly",
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        )
        merged = {"deploy_ratio": 1.0, "max_position_pct": 35.0}
        settings = {
            "harness": {
                "runtime_overlay_sources": ["policy"],
                "deploy_ratio_mode": "harness",
                "max_position_pct_mode": "harness",
            }
        }
        assert apply_whatif_buy_llm_optimal_to_policy(merged, state, settings=settings) is True
        assert merged["deploy_ratio"] == 0.6
        assert merged["max_position_pct"] == 30.0

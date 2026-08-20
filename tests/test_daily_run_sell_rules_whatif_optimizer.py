# -*- coding: utf-8
"""Tests for DeepSeek what-if sell-ratio optimizer."""

from unittest.mock import patch

import pytest

from agent_reach.daily_run.harness import HarnessEntry, HarnessState
from agent_reach.daily_run.harness_policy import resolve_harness_deep_loss_policy
from agent_reach.daily_run.sell_rules_whatif_optimizer import (
    apply_whatif_llm_optimal_to_policy,
    clamp_optimal_ratios,
    format_llm_optimal_policy_line,
    optimize_sell_rules_whatif_with_deepseek,
    parse_llm_optimal_policy_line,
)


class TestWhatIfOptimizerHelpers:
    def test_clamp_allows_full_clear_when_in_bounds(self):
        ratios = clamp_optimal_ratios(
            {"sell_ratio": 1.0, "non_deep_loss_sell_ratio": 0.95, "cover_ratio": 2.0}
        )
        assert ratios["sell_ratio"] == 1.0
        assert ratios["non_deep_loss_sell_ratio"] == 0.95
        assert ratios["cover_ratio"] == 1.5

    def test_parse_policy_line(self):
        line = format_llm_optimal_policy_line(
            {"sell_ratio": 0.55, "non_deep_loss_sell_ratio": 0.68, "cover_ratio": 1.05},
            rationale="test",
        )
        parsed = parse_llm_optimal_policy_line(line)
        assert parsed["sell_ratio"] == 0.55
        assert parsed["non_deep_loss_sell_ratio"] == 0.68
        assert parsed["cover_ratio"] == 1.05


class TestWhatIfDeepSeekOptimize:
    @patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value="deepseek")
    @patch("agent_reach.daily_run.llm_chat.chat_json")
    def test_optimize_returns_evidence(self, mock_chat, _provider):
        mock_chat.return_value = {
            "sell_ratio": 0.58,
            "non_deep_loss_sell_ratio": 0.72,
            "cover_ratio": 1.08,
            "rationale": "基准已实现更高，适度上调 partial sell",
            "confidence": 0.82,
        }
        report = {
            "week_start": "2026-08-18",
            "week_end": "2026-08-22",
            "weekly_pnl": -500.0,
            "sell_rules_whatif": {
                "skipped": False,
                "actual_realized_pnl": 2021.0,
                "hypothetical_realized_pnl": 1171.0,
                "realized_pnl_delta": -850.0,
                "rows": [],
            },
        }
        result = optimize_sell_rules_whatif_with_deepseek(report, settings={"sell_rules_whatif": {}})
        assert not result["skipped"]
        assert result["optimal"]["sell_ratio"] == 0.58
        assert any("DeepSeek 最优" in line for line in result["evidence"]["policy"])

    @patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None)
    def test_skips_without_api_key(self, _provider):
        result = optimize_sell_rules_whatif_with_deepseek(
            {"sell_rules_whatif": {"skipped": False, "rows": []}},
            settings={"sell_rules_whatif": {}},
        )
        assert result["skipped"] is True


class TestWhatIfLlmOptimalOverlay:
    def test_llm_optimal_overrides_step_rules(self):
        state = HarnessState()
        line = format_llm_optimal_policy_line(
            {"sell_ratio": 0.58, "non_deep_loss_sell_ratio": 0.72, "cover_ratio": 1.08}
        )
        state.entries["policy"]["llm"] = HarnessEntry(
            id="llm",
            kind="policy",
            title="llm optimal",
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
                "sell_ratio_mode": "harness",
                "non_deep_loss_sell_ratio_mode": "harness",
            },
            "pnl_overview": {
                "deep_loss_sell_ratio": 0.35,
                "non_deep_loss_sell_ratio": 0.5,
            },
        }
        policy = resolve_harness_deep_loss_policy(state, settings=settings)
        assert policy["sell_ratio"] == 0.58
        assert policy["non_deep_loss_sell_ratio"] == 0.72
        assert policy["cover_ratio"] == 1.08

    def test_apply_to_merged_dict(self):
        state = HarnessState()
        line = format_llm_optimal_policy_line(
            {"sell_ratio": 0.6, "non_deep_loss_sell_ratio": 0.7, "cover_ratio": 1.0}
        )
        state.entries["policy"]["llm"] = HarnessEntry(
            id="llm",
            kind="policy",
            title="llm",
            content=line,
            source="llm",
            job="sell_rules_whatif",
            evidence="weekly",
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        )
        merged = {"sell_ratio": 0.35, "non_deep_loss_sell_ratio": 0.5, "cover_ratio": 1.2}
        settings = {
            "harness": {
                "runtime_overlay_sources": ["policy"],
                "sell_ratio_mode": "harness",
                "non_deep_loss_sell_ratio_mode": "harness",
            }
        }
        assert apply_whatif_llm_optimal_to_policy(merged, state, settings=settings) is True
        assert merged["sell_ratio"] == 0.6
        assert merged["non_deep_loss_sell_ratio"] == 0.7
        assert merged["cover_ratio"] == 1.0

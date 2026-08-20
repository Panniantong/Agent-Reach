# -*- coding: utf-8
"""Tests for deep-loss threshold DeepSeek optimizer."""

from unittest.mock import patch

from agent_reach.daily_run.deep_loss_threshold_optimizer import (
    apply_deep_loss_threshold_llm_optimal_to_policy,
    format_deep_loss_threshold_policy_line,
    optimize_deep_loss_threshold_with_deepseek,
    parse_deep_loss_threshold_policy_line,
)
from agent_reach.daily_run.harness import HarnessEntry, HarnessState
from agent_reach.daily_run.harness_policy import resolve_harness_deep_loss_policy


class TestDeepLossThresholdOptimizer:
    def test_parse_policy_line(self):
        line = format_deep_loss_threshold_policy_line(
            {
                "loss_cny_threshold": 4200.0,
                "loss_pct_threshold": 8.0,
                "deep_loss_tier_multiplier": 2.2,
            }
        )
        parsed = parse_deep_loss_threshold_policy_line(line)
        assert parsed["loss_cny_threshold"] == 4200.0
        assert parsed["loss_pct_threshold"] == 8.0
        assert parsed["deep_loss_tier_multiplier"] == 2.2

    @patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value="deepseek")
    @patch("agent_reach.daily_run.llm_chat.chat_json")
    def test_optimize_returns_evidence(self, mock_chat, _provider):
        mock_chat.return_value = {
            "loss_cny_threshold": 4200,
            "loss_pct_threshold": 8,
            "deep_loss_tier_multiplier": 2.2,
            "rationale": "深亏处置偏慢",
            "confidence": 0.75,
        }
        pf = {
            "as_of": "2026-08-19",
            "sell_rules_whatif": {
                "skipped": False,
                "realized_pnl_delta": -300,
                "rows": [
                    {
                        "code": "000725",
                        "is_deep_loss": True,
                        "actual_sold": 0,
                        "hypothetical_sold": 500,
                    }
                ],
            },
        }
        result = optimize_deep_loss_threshold_with_deepseek(pf, settings={"deep_loss_threshold": {}})
        assert not result["skipped"]
        assert any("深亏阈值最优" in line for line in result["evidence"]["policy"])

    def test_llm_optimal_overrides_deep_loss_policy(self):
        state = HarnessState()
        line = format_deep_loss_threshold_policy_line(
            {
                "loss_cny_threshold": 4200.0,
                "loss_pct_threshold": 8.0,
                "deep_loss_tier_multiplier": 2.2,
            }
        )
        state.entries["policy"]["llm_deep"] = HarnessEntry(
            id="llm_deep",
            kind="policy",
            title="llm deep",
            content=line,
            source="llm",
            job="pnl_overview",
            evidence="close",
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        )
        settings = {
            "pnl_overview": {},
            "harness": {
                "enabled": True,
                "runtime_overlay": True,
                "loss_cny_threshold_mode": "harness",
                "loss_pct_threshold_mode": "harness",
                "deep_loss_tier_multiplier_mode": "harness",
                "runtime_overlay_sources": ["policy"],
            },
        }
        policy = resolve_harness_deep_loss_policy(state, settings=settings)
        assert policy["loss_cny_threshold"] == 4200.0
        assert policy["loss_pct_threshold"] == 8.0
        assert policy["deep_loss_tier_multiplier"] == 2.2

        merged = {"loss_cny_threshold": 5000.0}
        assert apply_deep_loss_threshold_llm_optimal_to_policy(merged, state, settings=settings)
        assert merged["loss_cny_threshold"] == 4200.0

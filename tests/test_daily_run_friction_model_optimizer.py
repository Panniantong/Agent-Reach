# -*- coding: utf-8
"""Tests for commission / slippage friction model DeepSeek optimizer."""

from unittest.mock import patch

from agent_reach.daily_run.friction_model_optimizer import (
    apply_friction_model_llm_optimal_to_policy,
    format_friction_model_policy_line,
    optimize_friction_model_with_deepseek,
    parse_friction_model_policy_line,
)
from agent_reach.daily_run.harness import HarnessEntry, HarnessState
from agent_reach.daily_run.harness_policy import resolve_harness_friction_model_policy


class TestFrictionModelOptimizer:
    def test_parse_policy_line(self):
        line = format_friction_model_policy_line(
            {"commission_rate": 0.0012, "slippage_rate": 0.0008},
            rationale="摩擦放行偏多",
        )
        parsed = parse_friction_model_policy_line(line)
        assert parsed["commission_rate"] == 0.0012
        assert parsed["slippage_rate"] == 0.0008

    @patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value="deepseek")
    @patch("agent_reach.daily_run.llm_chat.chat_json")
    def test_optimize_returns_evidence(self, mock_chat, _provider):
        mock_chat.return_value = {
            "commission_rate": 0.0012,
            "slippage_rate": 0.0008,
            "rationale": "摩擦放行偏多",
            "confidence": 0.7,
        }
        pf = {
            "as_of": "2026-08-19",
            "intraday_friction_whatif": {
                "skipped": False,
                "friction_would_pass": 3,
                "trend_mismatch": 0,
                "rows": [],
            },
        }
        result = optimize_friction_model_with_deepseek(pf, settings={"friction_model": {}})
        assert not result["skipped"]
        assert any("摩擦模型最优" in line for line in result["evidence"]["policy"])

    def test_llm_optimal_overrides_runtime(self):
        state = HarnessState()
        line = format_friction_model_policy_line(
            {"commission_rate": 0.0012, "slippage_rate": 0.0008},
        )
        state.entries["policy"]["llm_friction_model"] = HarnessEntry(
            id="llm_friction_model",
            kind="policy",
            title="llm friction model",
            content=line,
            source="llm",
            job="intraday_friction",
            evidence="close",
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        )
        settings = {
            "trading": {"commission_rate": 0.0015, "slippage_rate": 0.001},
            "harness": {
                "enabled": True,
                "runtime_overlay": True,
                "threshold_evolution_mode": "harness",
                "runtime_overlay_sources": ["policy"],
            },
        }
        effective = resolve_harness_friction_model_policy(state, settings=settings)
        assert effective["commission_rate"] == 0.0012
        assert effective["slippage_rate"] == 0.0008

        merged = {"commission_rate": 0.0015, "slippage_rate": 0.001}
        assert apply_friction_model_llm_optimal_to_policy(merged, state, settings=settings)
        assert merged["commission_rate"] == 0.0012
        assert merged["slippage_rate"] == 0.0008

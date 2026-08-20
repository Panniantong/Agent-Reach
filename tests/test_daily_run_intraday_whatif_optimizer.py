# -*- coding: utf-8
"""Tests for intraday friction what-if and DeepSeek optimizer."""

from unittest.mock import patch

from agent_reach.daily_run.harness import HarnessEntry, HarnessState
from agent_reach.daily_run.harness_policy import (
    resolve_harness_flat_overrides,
    resolve_harness_trend_policy,
)
from agent_reach.daily_run.intraday_whatif_optimizer import (
    apply_intraday_friction_llm_optimal_to_flat,
    apply_intraday_friction_llm_optimal_to_trend,
    format_intraday_friction_policy_line,
    optimize_intraday_friction_with_deepseek,
    parse_intraday_friction_policy_line,
)
from agent_reach.daily_run.sell_rules_whatif import build_intraday_friction_whatif


class TestIntradayFrictionWhatIf:
    def test_friction_divergence_row(self):
        morning = {
            "portfolio": {
                "cash": 200000.0,
                "total": 200000.0,
                "holdings": [],
                "watchlist": [{"code": "000725", "name": "京东方A"}],
            },
        }
        close = {
            "portfolio": {
                "cash": 200000.0,
                "total": 200000.0,
                "holdings": [],
                "watchlist": [{"code": "000725", "name": "京东方A"}],
            },
        }
        summary = {
            "as_of": "2026-08-19",
            "intraday_trades": [
                {
                    "action": "hold",
                    "lookback_mss": 65,
                    "trend": "rising",
                    "verdict": "可做",
                    "mss_final": 65,
                    "code": "000725",
                    "name": "京东方A",
                    "blocked": False,
                    "friction_blocked": True,
                }
            ],
        }
        settings = {
            "thresholds": {"max_snapshot_age_hours": 24},
            "trading": {"friction_min_return_pct": 0.005, "min_deploy_cash": 1000},
            "intraday": {"trend_min_points": 2, "trend_delta_threshold": 1.0},
            "harness": {"threshold_evolution_mode": "harness"},
        }
        result = build_intraday_friction_whatif(
            summary=summary,
            baseline=morning,
            current=close,
            settings=settings,
        )
        assert not result.skipped
        assert result.friction_blocked_actual == 1
        assert len(result.rows) >= 1


class TestIntradayFrictionOptimizer:
    def test_parse_policy_line(self):
        line = format_intraday_friction_policy_line(
            {
                "friction_min_return_pct": 0.004,
                "trend_min_points": 2.0,
                "trend_delta_threshold": 0.9,
            }
        )
        parsed = parse_intraday_friction_policy_line(line)
        assert parsed["friction_min_return_pct"] == 0.004
        assert parsed["trend_delta_threshold"] == 0.9

    @patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value="deepseek")
    @patch("agent_reach.daily_run.llm_chat.chat_json")
    def test_optimize_returns_evidence(self, mock_chat, _provider):
        mock_chat.return_value = {
            "friction_min_return_pct": 0.004,
            "trend_min_points": 2,
            "trend_delta_threshold": 0.9,
            "rationale": "摩擦放行偏多",
            "confidence": 0.7,
        }
        pf = {
            "as_of": "2026-08-19",
            "intraday_friction_whatif": {
                "skipped": False,
                "friction_would_pass": 3,
                "trend_mismatch": 1,
                "rows": [],
            },
        }
        result = optimize_intraday_friction_with_deepseek(pf, settings={"intraday_whatif": {}})
        assert not result["skipped"]
        assert any("摩擦趋势最优" in line for line in result["evidence"]["policy"])

    def test_llm_optimal_overrides_runtime(self):
        state = HarnessState()
        line = format_intraday_friction_policy_line(
            {
                "friction_min_return_pct": 0.004,
                "trend_min_points": 3.0,
                "trend_delta_threshold": 0.9,
            }
        )
        state.entries["policy"]["llm_intraday"] = HarnessEntry(
            id="llm_intraday",
            kind="policy",
            title="llm intraday",
            content=line,
            source="llm",
            job="intraday_friction",
            evidence="close",
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        )
        settings = {
            "thresholds": {"max_snapshot_age_hours": 24},
            "harness": {
                "enabled": True,
                "runtime_overlay": True,
                "threshold_evolution_mode": "harness",
                "trend_min_points_mode": "harness",
                "trend_delta_threshold_mode": "harness",
                "runtime_overlay_sources": ["policy"],
            },
        }
        flat = resolve_harness_flat_overrides(
            state,
            {"max_snapshot_age_hours": 24},
            settings=settings,
        )
        assert flat["friction_min_return_pct"] == 0.004
        trend = resolve_harness_trend_policy(state, settings=settings)
        assert trend["trend_min_points"] == 3.0
        assert trend["trend_delta_threshold"] == 0.9

        merged = {"friction_min_return_pct": 0.005}
        assert apply_intraday_friction_llm_optimal_to_flat(merged, state, settings=settings)
        assert merged["friction_min_return_pct"] == 0.004
        trend_m = {"trend_min_points": 2.0, "trend_delta_threshold": 1.0}
        assert apply_intraday_friction_llm_optimal_to_trend(trend_m, state, settings=settings)
        assert trend_m["trend_min_points"] == 3.0

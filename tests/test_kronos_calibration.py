# -*- coding: utf-8
"""Tests for Kronos error ledger, inference policy, and calibrate harness."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from datetime import date, timedelta

import pytest

from agent_reach.daily_run.kronos_calibrate_harness import (
    kronos_calibrate_to_harness_evidence,
    run_kronos_inference_grid,
)
from agent_reach.daily_run.kronos_calibration import (
    append_kronos_error_ledger,
    build_kronos_ledger_entries,
    summarize_kronos_ledger,
)
from agent_reach.daily_run.kronos_inference_policy import (
    format_kronos_inference_policy_line,
    format_kronos_symbol_blend_policy_line,
    parse_kronos_inference_policy_line,
    parse_kronos_symbol_blend_policy_line,
    resolve_harness_kronos_inference_policy,
    resolve_harness_kronos_symbol_blend,
    resolve_symbol_blend_weight,
)
from agent_reach.daily_run.week_forecast_tracker import ForecastDayReview, SymbolEval


def _sample_review() -> ForecastDayReview:
    return ForecastDayReview(
        date="2026-09-15",
        symbol_evals=[
            SymbolEval(
                code="688008",
                name="澜起科技",
                role="holding",
                predicted_direction="up",
                predicted_range=[-1.0, 2.0],
                actual_change_pct=1.5,
                hit=True,
                error_pct=0.3,
            )
        ],
        symbol_hits=1,
        symbol_total=1,
        accuracy=1.0,
        kronos_review={"mean_error_pct": 0.8, "divergence_count": 1},
    )


def _sample_forecast() -> dict:
    return {
        "kronos_paths": {
            "688008": {
                "available": True,
                "days": {
                    "2026-09-15": {
                        "change_pct": 0.7,
                        "direction": "up",
                    }
                },
            }
        }
    }


class TestKronosErrorLedger:
    def test_build_entries(self):
        rows = build_kronos_ledger_entries(_sample_review(), _sample_forecast())
        assert len(rows) == 1
        assert rows[0]["code"] == "688008"
        assert rows[0]["error_pct"] == pytest.approx(0.8, abs=0.01)
        assert rows[0]["direction_hit"] is True

    @patch("agent_reach.daily_run.kronos_predictor.is_kronos_enabled", return_value=True)
    def test_append_ledger(self, _enabled, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.kronos_calibration.error_ledger_path",
            lambda: tmp_path / "error_ledger.jsonl",
        )
        out = append_kronos_error_ledger(
            _sample_review(),
            _sample_forecast(),
            settings={"kronos": {"enabled": True}},
        )
        assert out["skipped"] is False
        assert out["rows"] == 1
        lines = (tmp_path / "error_ledger.jsonl").read_text(encoding="utf-8").strip().splitlines()
        row = json.loads(lines[0])
        assert row["name"] == "澜起科技"

    def test_summarize_divergence_heavy(self):
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        rows = [
            {
                "date": yesterday,
                "code": "603986",
                "error_pct": -2.0,
                "direction_hit": False,
            },
            {
                "date": today,
                "code": "603986",
                "error_pct": 2.5,
                "direction_hit": False,
            },
        ]
        summary = summarize_kronos_ledger(rows, lookback_days=30)
        assert summary["rows"] == 2
        assert "603986" in summary["divergence_heavy_codes"]


class TestKronosInferencePolicy:
    def test_format_and_parse_inference_line(self):
        line = format_kronos_inference_policy_line(
            {
                "inference_T": 0.6,
                "inference_top_p": 0.9,
                "inference_sample_count": 5,
                "week_forecast_blend_weight": 0.35,
            },
            rationale="hold-out",
        )
        parsed = parse_kronos_inference_policy_line(line)
        assert parsed is not None
        assert parsed["inference_T"] == pytest.approx(0.6)
        assert parsed["week_forecast_blend_weight"] == pytest.approx(0.35)

    def test_symbol_blend_line(self):
        line = format_kronos_symbol_blend_policy_line({"688008": 0.25, "603986": 0.3})
        parsed = parse_kronos_symbol_blend_policy_line(line)
        assert parsed["688008"] == pytest.approx(0.25)
        assert parsed["603986"] == pytest.approx(0.3)

    def test_resolve_symbol_blend_weight(self):
        settings = {
            "kronos": {
                "enabled": True,
                "inference_mode": "fixed",
                "week_forecast_blend_weight": 0.35,
            },
            "harness_runtime": {
                "kronos_symbol_blend": {"688008": 0.22},
            },
        }
        assert resolve_symbol_blend_weight("688008", settings) == pytest.approx(0.22)
        assert resolve_symbol_blend_weight("603986", settings) == pytest.approx(0.35)

    def test_resolve_harness_inference_from_policy(self):
        state = MagicMock()
        state.entries = {
            "policy": {
                "p1": MagicMock(
                    title="kronos",
                    content=(
                        "Kronos inference最优：inference_T=0.8 inference_top_p=0.9 "
                        "inference_sample_count=3 week_forecast_blend_weight=0.25"
                    ),
                    updated_at="2026-09-15",
                )
            }
        }
        settings = {
            "harness": {"enabled": True, "overlay": {"policy": True}},
            "kronos": {"enabled": True, "inference_mode": "harness"},
        }
        resolved = resolve_harness_kronos_inference_policy(state, settings=settings)
        assert resolved["inference_T"] == pytest.approx(0.8)
        assert resolved["inference_sample_count"] == pytest.approx(3.0)

    def test_resolve_harness_symbol_blend(self):
        state = MagicMock()
        state.entries = {
            "policy": {
                "p1": MagicMock(
                    title="blend",
                    content="Kronos symbol_blend：688008=0.22 603986=0.28",
                    updated_at="2026-09-15",
                )
            }
        }
        settings = {
            "harness": {"enabled": True, "overlay": {"policy": True}},
            "kronos": {"enabled": True, "inference_mode": "harness"},
        }
        blends = resolve_harness_kronos_symbol_blend(state, settings=settings)
        assert blends["688008"] == pytest.approx(0.22)


class TestKronosCalibrateHarness:
    @patch("agent_reach.daily_run.kronos_holdout_backtest.run_kronos_holdout_backtest")
    def test_grid_picks_best_params(self, mock_backtest):
        mock_backtest.side_effect = [
            {
                "available": True,
                "summary": {
                    "direction_hit_rate": 0.4,
                    "mean_abs_close_error_pct": 3.0,
                    "mean_change_error_pct": 1.0,
                },
            },
            {
                "available": True,
                "summary": {
                    "direction_hit_rate": 0.8,
                    "mean_abs_close_error_pct": 1.0,
                    "mean_change_error_pct": 0.2,
                },
            },
        ]
        settings = {
            "kronos": {
                "enabled": True,
                "calibrate": {
                    "grid": {
                        "inference_T": [0.4, 0.8],
                        "inference_sample_count": [5],
                        "week_forecast_blend_weight": [0.35],
                    }
                },
            }
        }
        result = run_kronos_inference_grid(["688008"], settings=settings)
        assert result["skipped"] is False
        assert result["best"]["params"]["inference_T"] == pytest.approx(0.8)

    def test_harness_evidence_policy_line(self):
        evidence = kronos_calibrate_to_harness_evidence(
            {
                "skipped": False,
                "trials_run": 6,
                "trials_requested": 6,
                "codes": ["688008"],
                "best": {
                    "loss": 1.23,
                    "params": {
                        "inference_T": 0.6,
                        "inference_top_p": 0.9,
                        "inference_sample_count": 5,
                        "week_forecast_blend_weight": 0.35,
                    },
                },
                "ledger_summary": {"divergence_heavy_codes": ["603986"]},
            }
        )
        assert evidence["policy"]
        assert "Kronos inference最优" in evidence["policy"][0]
        assert any("symbol_blend" in line for line in evidence["policy"])

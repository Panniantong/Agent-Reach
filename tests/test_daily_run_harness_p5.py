# -*- coding: utf-8
"""Tests for forge numeric gates and weekly harness narrative."""

import pytest

from agent_reach.daily_run.harness import format_harness_push_markdown, refine_after_job
from agent_reach.daily_run.harness_forge_gates import (
    evaluate_forge_gate,
    validate_forecast_calibrate_forge,
    validate_pnl_target_forge,
)
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement
from agent_reach.daily_run.harness_weekly_narrative import (
    build_weekly_harness_narrative,
    format_weekly_harness_narrative_markdown,
    load_apply_audit_in_window,
)


@pytest.fixture
def harness_tmp(monkeypatch, tmp_path):
    hdir = tmp_path / "harness"
    hdir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("agent_reach.daily_run.harness.harness_dir", lambda: hdir)
    monkeypatch.setattr("agent_reach.daily_run.harness._state_path", lambda: hdir / "harness_state.json")
    monkeypatch.setattr("agent_reach.daily_run.harness._refinements_path", lambda: hdir / "refinements.jsonl")
    monkeypatch.setattr("agent_reach.daily_run.harness_apply_gate._audit_path", lambda: hdir / "apply_audit.jsonl")
    monkeypatch.setattr("agent_reach.daily_run.harness_snapshot.harness_dir", lambda: hdir)
    monkeypatch.setattr("agent_reach.daily_run.harness_snapshot._state_path", lambda: hdir / "harness_state.json")
    return hdir


class TestForgeGates:
    def test_pnl_target_rejects_oversized_target(self):
        result = validate_pnl_target_forge(
            {
                "next_target": {
                    "target_pnl_cny": 999999,
                    "target_pnl_pct": 50.0,
                    "baseline_nav": 100000,
                }
            },
            settings={"harness": {"forge_gates": {"enabled": True}}},
        )
        assert result.passed is False
        assert result.violations

    def test_pnl_target_accepts_normal_target(self):
        result = validate_pnl_target_forge(
            {
                "next_target": {
                    "target_pnl_cny": 500,
                    "target_pnl_pct": 0.5,
                    "baseline_nav": 100000,
                }
            },
            settings={"harness": {"forge_gates": {"enabled": True}}},
        )
        assert result.passed is True

    def test_forecast_rejects_vol_scale_out_of_bounds(self):
        result = validate_forecast_calibrate_forge(
            {"calibration_used": {"vol_scale": 9.9, "bias_pct": 0.1}},
            settings={"week_forecast": {"min_vol_scale": 0.6, "max_vol_scale": 1.6, "max_bias_pct": 3.0}},
        )
        assert result.passed is False

    def test_apply_skill_refinement_skips_on_forge_fail(self, harness_tmp):
        result = apply_skill_refinement(
            "pnl_target",
            {
                "memory": ["bad target"],
                "forge_domain": {
                    "next_target": {
                        "target_pnl_cny": 999999,
                        "target_pnl_pct": 50.0,
                        "baseline_nav": 100000,
                    }
                },
            },
            settings={"harness": {"enabled": True, "jobs": {"pnl_target": True}}},
        )
        assert result.get("skipped") is True
        assert result.get("reason") == "forge_gate_failed"

    def test_apply_skill_refinement_passes_with_valid_forge(self, harness_tmp):
        result = apply_skill_refinement(
            "pnl_target",
            {
                "memory": ["ok target"],
                "summary": "pnl_target ok",
                "forge_domain": {
                    "next_target": {
                        "target_pnl_cny": 500,
                        "target_pnl_pct": 0.5,
                        "baseline_nav": 100000,
                    }
                },
            },
            settings={"harness": {"enabled": True, "jobs": {"pnl_target": True}}},
        )
        assert result.get("skipped") is False
        assert result.get("refinement_id")
        assert result.get("forge_gate", {}).get("passed") is True

    def test_evaluate_forge_gate_disabled_returns_none(self):
        assert (
            evaluate_forge_gate(
                "pnl_target",
                {"forge_domain": {"next_target": {"target_pnl_cny": 999999}}},
                settings={"harness": {"forge_gates": {"enabled": False}}},
            )
            is None
        )


class TestWeeklyHarnessNarrative:
    def test_load_apply_audit_in_window(self, harness_tmp):
        audit_path = harness_tmp / "apply_audit.jsonl"
        audit_path.write_text(
            "\n".join(
                [
                    '{"at":"2026-08-11T10:00:00+00:00","job":"close","changes":2,"gate":{}}',
                    '{"at":"2026-08-18T10:00:00+00:00","job":"verify","changes":1,"gate":{"blocked_kinds":["policy"]}}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        rows = load_apply_audit_in_window(
            week_start="2026-08-11",
            week_end="2026-08-18",
        )
        assert len(rows) == 2

    def test_build_and_format_weekly_narrative(self, harness_tmp):
        audit_path = harness_tmp / "apply_audit.jsonl"
        audit_path.write_text(
            '{"at":"2026-08-15T09:00:00+00:00","job":"close","changes":3,"gate":{}}\n',
            encoding="utf-8",
        )
        narrative = build_weekly_harness_narrative(
            week_start="2026-08-11",
            week_end="2026-08-17",
            harness_result={"layer_a": {"refinement_id": "refine_0001", "changes": 2}},
            settings={"harness": {"weekly_narrative": {"enabled": True}}},
        )
        assert narrative["audit_events"] == 1
        assert narrative["total_changes"] == 3
        md = format_weekly_harness_narrative_markdown(narrative)
        assert "Harness 周度叙事" in md
        assert "close×1" in md

    def test_weekly_card_appends_narrative(self, harness_tmp):
        audit_path = harness_tmp / "apply_audit.jsonl"
        audit_path.write_text(
            '{"at":"2026-08-15T09:00:00+00:00","job":"weekly","changes":1,"gate":{}}\n',
            encoding="utf-8",
        )
        refine_after_job(
            "weekly",
            evidence={"memory": ["weekly test"], "summary": "weekly test"},
            settings={"harness": {"enabled": True, "jobs": {"weekly": True}}},
        )
        md = format_harness_push_markdown(
            {"layer_a": {"refinement_id": "refine_0001", "changes": 1, "planner": "deterministic"}},
            job="weekly",
            week_start="2026-08-11",
            week_end="2026-08-17",
            settings={"harness": {"weekly_narrative": {"enabled": True, "append_to_weekly_card": True}}},
        )
        assert "Harness 周度叙事" in md

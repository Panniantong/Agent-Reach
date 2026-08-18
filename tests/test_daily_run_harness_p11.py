# -*- coding: utf-8
"""Tests for finance research, study registry, branch overlay, narrative extensions."""

import json
import pytest

from agent_reach.daily_run.finance_research_harness import apply_finance_research_harness_refinement
from agent_reach.daily_run.forecast_harness_skills import run_forecast_harness_refinements
from agent_reach.daily_run.harness_finance import build_finance_research_workflow
from agent_reach.daily_run.harness_git import branch_slug, resolve_harness_paths
from agent_reach.daily_run.harness_study_registry import load_study_registry, register_study
from agent_reach.daily_run.harness_weekly_narrative import build_weekly_harness_narrative
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


@pytest.fixture
def harness_tmp(monkeypatch, tmp_path):
    hdir = tmp_path / "harness"
    hdir.mkdir(parents=True, exist_ok=True)
    branch_dir = hdir / "branches" / "feature-x"
    branch_dir.mkdir(parents=True, exist_ok=True)
    audit = hdir / "apply_audit.jsonl"

    def _paths(settings=None):
        return {
            "root": branch_dir,
            "branch": "feature-x",
            "state": branch_dir / "harness_state.json",
            "refinements": branch_dir / "refinements.jsonl",
            "snapshots": branch_dir / "snapshots",
            "registry": branch_dir / "study_registry.json",
            "audit": audit,
        }

    monkeypatch.setattr("agent_reach.daily_run.harness_git.resolve_harness_paths", _paths)
    monkeypatch.setattr("agent_reach.daily_run.harness_git.resolve_harness_state_path", lambda s=None: _paths()["state"])
    monkeypatch.setattr("agent_reach.daily_run.harness_git.detect_git_branch", lambda **kw: "feature-x")
    monkeypatch.setattr("agent_reach.daily_run.harness.harness_dir", lambda: branch_dir)
    monkeypatch.setattr("agent_reach.daily_run.harness._state_path", lambda: branch_dir / "harness_state.json")
    monkeypatch.setattr("agent_reach.daily_run.harness._refinements_path", lambda: branch_dir / "refinements.jsonl")
    monkeypatch.setattr("agent_reach.daily_run.harness_apply_gate._audit_path", lambda: audit)
    monkeypatch.setattr("agent_reach.daily_run.harness_snapshot.harness_dir", lambda: branch_dir)
    monkeypatch.setattr("agent_reach.daily_run.harness_snapshot._state_path", lambda: branch_dir / "harness_state.json")
    return branch_dir


WEEKLY = {
    "week_start": "2026-08-11",
    "week_end": "2026-08-15",
    "weekly_pnl": 5000.0,
    "start_total": 100000.0,
    "end_total": 105000.0,
    "holdings": [{"code": "600584", "name": "长电", "week_chg": 3000.0}],
    "skill_research": [{"title": "半导体周期", "summary": "景气回升", "url": "https://example.com"}],
    "process_improvements": [{"priority": "high", "title": "盘中 scan 覆盖率"}],
}


class TestFinanceResearchWorkflow:
    def test_build_workflow_queries(self):
        workflow = build_finance_research_workflow(WEEKLY)
        assert workflow["queries"]
        assert workflow["sources"]
        assert workflow["steps"]

    def test_finance_research_harness_refines(self, harness_tmp):
        result = apply_finance_research_harness_refinement(
            WEEKLY,
            settings={
                "finance_research": {"enabled": True},
                "harness": {"enabled": True, "jobs": {"finance_research": True}},
            },
        )
        assert result.get("skipped") is False
        assert result.get("workflow", {}).get("queries")


class TestStudyRegistry:
    def test_register_optimize_study(self, harness_tmp):
        row = register_study(
            "optimize",
            {
                "objective": "excess_return",
                "best_score": 0.12,
                "trials": 8,
                "metrics": {"total_return": 0.1, "max_drawdown": 0.04},
                "best_params": {"macro_veto": 40, "aggressive_entry": 55},
            },
            settings={"harness": {"study_registry": {"enabled": True}}},
        )
        assert row
        data = load_study_registry()
        assert len(data["studies"]) == 1
        assert data["studies"][0]["git_branch"] == "feature-x"

    def test_optimize_refine_registers_study(self, harness_tmp):
        result = apply_skill_refinement(
            "optimize",
            {
                "memory": ["optimize ok"],
                "summary": "optimize ok",
                "forge_domain": {
                    "objective": "excess_return",
                    "best_score": 0.12,
                    "trials": 8,
                    "metrics": {"total_return": 0.1, "max_drawdown": 0.04},
                    "best_params": {"macro_veto": 40, "aggressive_entry": 55},
                },
                "rigor_domain": {
                    "objective": "excess_return",
                    "best_score": 0.12,
                    "trials": 8,
                    "metrics": {"total_return": 0.1, "max_drawdown": 0.04},
                    "best_params": {"macro_veto": 40, "aggressive_entry": 55},
                },
            },
            settings={"harness": {"enabled": True, "jobs": {"optimize": True}}},
        )
        assert result.get("study_registry")
        assert load_study_registry()["studies"]


class TestBranchOverlay:
    def test_branch_slug(self):
        assert branch_slug("fix/capital-events") == "fix-capital-events"

    def test_resolve_paths_uses_branch_dir(self, harness_tmp, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.harness_git.branch_overlay_cfg",
            lambda s=None: {"enabled": True, "use_root_for_main": False, "main_names": {"main"}},
        )
        paths = resolve_harness_paths({"harness": {"branch_overlay": {"enabled": True}}})
        assert "branches" in str(paths["state"])


class TestWeeklyNarrativeExtensions:
    def test_narrative_counts_finance_and_doctor(self, harness_tmp):
        from agent_reach.daily_run.harness_apply_gate import record_apply_audit

        record_apply_audit(
            job="finance_statements",
            changes=2,
            injection_meta={"context_doctor": {"memory": {"dropped_count": 1}}},
        )
        register_study(
            "optimize",
            {
                "objective": "excess_return",
                "best_score": 0.1,
                "trials": 5,
                "metrics": {"total_return": 0.1, "max_drawdown": 0.03},
                "best_params": {"macro_veto": 40, "aggressive_entry": 55},
            },
        )
        narrative = build_weekly_harness_narrative(
            week_start="2026-08-11",
            week_end="2026-08-18",
        )
        assert narrative["audit_events"] >= 1
        assert narrative["finance_jobs"] >= 1
        assert narrative["context_doctor_drops"] >= 1
        assert narrative["study_registry_entries"] >= 1


class TestForecastResearch:
    def test_forecast_runs_finance_research(self, harness_tmp):
        forecast = {
            "week_start": "2026-08-18",
            "week_end": "2026-08-22",
            "notes": ["MSS 预测偏强，需校准 base_spread"],
            "calibration_used": {"vol_scale": 1.1, "bias_pct": 0.2},
        }
        report = run_forecast_harness_refinements(
            forecast,
            settings={
                "finance_research": {"enabled": True, "run_on_forecast": True},
                "harness": {"enabled": True, "jobs": {"finance_research": True, "forecast_calibrate": True}},
            },
        )
        assert report.finance_research.get("skipped") is False

# -*- coding: utf-8
"""Tests for weekly finance_variance and finance_close_plan harness jobs."""

import pytest

from agent_reach.daily_run.finance_close_plan_harness import apply_finance_close_plan_harness_refinement
from agent_reach.daily_run.finance_variance_harness import apply_finance_variance_harness_refinement
from agent_reach.daily_run.harness_finance import analyze_weekly_variance_bridge, build_close_management_plan
from agent_reach.daily_run.weekly_harness_skills import run_weekly_harness_refinements


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


WEEKLY_REPORT = {
    "week_start": "2026-08-11",
    "week_end": "2026-08-15",
    "start_total": 100000.0,
    "end_total": 101200.0,
    "weekly_pnl": 1200.0,
    "weekly_pnl_pct": 1.2,
    "stock_pnl": 900.0,
    "cash_pnl": 300.0,
    "holdings": [
        {"code": "600584", "name": "长电科技", "week_chg": 800.0},
        {"code": "000725", "name": "京东方A", "week_chg": 100.0},
    ],
    "daily_totals": [
        {"date": "2026-08-11", "job": "close", "total": 100200.0},
        {"date": "2026-08-12", "job": "close", "total": 100500.0},
        {"date": "2026-08-13", "job": "close", "total": 100900.0},
        {"date": "2026-08-14", "job": "close", "total": 101000.0},
        {"date": "2026-08-15", "job": "close", "total": 101200.0},
    ],
    "process_improvements": [{"title": "补全 close manifest", "priority": "high"}],
}


class TestWeeklyFinanceHarness:
    def test_weekly_variance_bridge_reconciles(self):
        bridge = analyze_weekly_variance_bridge(WEEKLY_REPORT)
        assert bridge.reconciled is True
        assert bridge.total_variance == 1200.0

    def test_close_management_plan_builds_tasks(self):
        plan = build_close_management_plan(WEEKLY_REPORT)
        assert len(plan["tasks"]) >= 5
        assert plan["variance"]["reconciled"] is True

    def test_finance_variance_harness_refines(self, harness_tmp):
        result = apply_finance_variance_harness_refinement(
            WEEKLY_REPORT,
            settings={
                "finance_variance": {"enabled": True},
                "harness": {"enabled": True, "jobs": {"finance_variance": True}},
            },
        )
        assert result.get("skipped") is False
        assert result.get("refinement_id")

    def test_finance_close_plan_harness_refines(self, harness_tmp):
        result = apply_finance_close_plan_harness_refinement(
            WEEKLY_REPORT,
            settings={
                "finance_close_plan": {"enabled": True},
                "harness": {"enabled": True, "jobs": {"finance_close_plan": True}},
            },
        )
        assert result.get("skipped") is False
        assert result.get("close_plan", {}).get("tasks")

    def test_weekly_harness_orchestrator(self, harness_tmp):
        report = run_weekly_harness_refinements(
            WEEKLY_REPORT,
            settings={
                "finance_variance": {"enabled": True},
                "finance_close_plan": {"enabled": True},
                "harness": {
                    "enabled": True,
                    "jobs": {"finance_variance": True, "finance_close_plan": True, "skill_closure": True},
                },
            },
        )
        assert not report.finance_variance.get("skipped")
        assert not report.finance_close_plan.get("skipped")

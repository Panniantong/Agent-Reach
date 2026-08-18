# -*- coding: utf-8
"""Tests for expert_consensus weekly rollup and MSS close path."""

import pytest

from agent_reach.daily_run.expert_consensus_harness import apply_expert_consensus_harness_refinement
from agent_reach.daily_run.expert_consensus_weekly_harness import apply_expert_consensus_weekly_harness_refinement
from agent_reach.daily_run.harness_experts import aggregate_expert_consensus_audit, detect_expert_mode
from agent_reach.daily_run.harness_weekly_narrative import build_weekly_harness_narrative
from agent_reach.daily_run.weekly_harness_skills import run_weekly_harness_refinements
from agent_reach.daily_run.plugins.loader import MSS_EXPERT_NAMES


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


def _mss_snapshot() -> dict:
    results = [
        {"name": name, "score": 55.0, "summary": name, "success": True}
        for name in MSS_EXPERT_NAMES
    ]
    return {
        "code": "688008",
        "name": "澜起科技",
        "expert_results": results,
        "expert_scores": {r["name"]: r["score"] for r in results},
        "mss_breakdown": {"technical": 50, "quant": 52, "risk": 48, "global": 40},
    }


class TestExpertMode:
    def test_detect_mss_only(self):
        assert detect_expert_mode(_mss_snapshot()) == "mss_only"

    def test_detect_full_team(self):
        snap = _mss_snapshot()
        snap["expert_results"].append({"name": "identifier", "score": 50, "summary": "ok", "success": True})
        assert detect_expert_mode(snap) == "full_team"

    def test_mss_harness_tags_mode(self, harness_tmp):
        result = apply_expert_consensus_harness_refinement(
            _mss_snapshot(),
            settings={
                "expert_consensus": {"enabled": True, "max_mss_drift_flags": 8},
                "harness": {"enabled": True, "jobs": {"expert_consensus": True}},
            },
            workflow="close",
        )
        review = result.get("checks", {}).get("review") or {}
        assert review.get("expert_mode") == "mss_only"


class TestExpertConsensusWeekly:
    def test_aggregate_audit_rows(self):
        rows = [
            {
                "job": "expert_consensus",
                "status": "applied",
                "gate": {
                    "verification_signals": [
                        "expert_conflicts",
                        "expert_mss_drift",
                        "expert_mode_mss_only",
                        "expert_workflow_close",
                    ]
                },
            },
            {
                "job": "expert_consensus",
                "status": "skipped",
                "reason": "forge_gate_failed",
                "gate": {"verification_signals": ["expert_identifier_blocked"]},
            },
        ]
        agg = aggregate_expert_consensus_audit(rows)
        assert agg["runs"] == 2
        assert agg["conflicts"] == 1
        assert agg["drift"] == 1
        assert agg["blocked"] == 1
        assert agg["mss_only"] == 1

    def test_weekly_harness_refines(self, harness_tmp):
        from agent_reach.daily_run.harness_apply_gate import record_apply_audit

        record_apply_audit(
            job="expert_consensus",
            changes=2,
            gate={
                "verification_signals": [
                    "expert_conflicts",
                    "expert_mode_full_team",
                    "expert_workflow_morning",
                ]
            },
        )
        report = {"week_start": "2026-08-11", "week_end": "2026-08-18"}
        result = apply_expert_consensus_weekly_harness_refinement(
            report,
            settings={
                "expert_consensus": {"enabled": True, "weekly": {"enabled": True}},
                "harness": {"enabled": True, "jobs": {"expert_consensus_weekly": True}},
            },
        )
        assert result.get("skipped") is False
        assert result.get("aggregate", {}).get("runs") >= 1

    def test_weekly_orchestrator_wires_job(self, harness_tmp):
        from agent_reach.daily_run.harness_apply_gate import record_apply_audit

        record_apply_audit(
            job="expert_consensus",
            changes=1,
            gate={"verification_signals": ["expert_mss_drift", "expert_workflow_close"]},
        )
        report = run_weekly_harness_refinements(
            {"week_start": "2026-08-11", "week_end": "2026-08-18", "weekly_pnl_pct": 0.5},
            settings={
                "expert_consensus": {"enabled": True},
                "harness": {
                    "enabled": True,
                    "jobs": {
                        "finance_variance": False,
                        "finance_statements": False,
                        "finance_research": False,
                        "finance_close_plan": False,
                        "expert_consensus_weekly": True,
                        "run_guard": False,
                    },
                },
            },
            skip_run_guard=True,
        )
        assert report.expert_consensus_weekly.get("skipped") is False

    def test_weekly_narrative_expert_counters(self, harness_tmp):
        from agent_reach.daily_run.harness_apply_gate import record_apply_audit

        record_apply_audit(
            job="expert_consensus",
            changes=1,
            gate={"verification_signals": ["expert_conflicts", "expert_mss_drift"]},
        )
        record_apply_audit(job="expert_consensus_weekly", changes=3)
        narrative = build_weekly_harness_narrative(
            week_start="2026-08-11",
            week_end="2026-08-18",
        )
        assert narrative["expert_consensus_runs"] >= 1
        assert narrative["expert_conflict_sessions"] >= 1
        assert narrative["expert_drift_sessions"] >= 1
        assert narrative["expert_consensus_weekly_runs"] >= 1

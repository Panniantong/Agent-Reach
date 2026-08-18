# -*- coding: utf-8
"""Tests for expert_consensus harness (Team-First → policy closed loop)."""

import pytest

from agent_reach.daily_run.expert_consensus_harness import (
    apply_expert_consensus_harness_refinement,
    expert_consensus_to_harness_evidence,
)
from agent_reach.daily_run.harness_experts import build_expert_consensus_review, run_expert_consensus_checks
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement
from agent_reach.daily_run.close_harness_skills import run_close_harness_refinements
from agent_reach.daily_run.team import supervisor_review


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


def _conflict_snapshot() -> dict:
    results = [
        {"name": "technical", "score": 68, "summary": "t", "success": True},
        {"name": "risk", "score": 36, "summary": "r", "success": True},
        {"name": "macro", "score": 55, "summary": "m", "success": True},
        {"name": "sentiment", "score": 30, "summary": "s", "success": True},
    ]
    review = supervisor_review({"expert_results": results}, {})
    return {
        "name": "澜起科技",
        "code": "688008",
        "expert_results": results,
        "expert_scores": {r["name"]: r["score"] for r in results},
        "team_review": review.to_dict(),
        "mss_breakdown": {"global": 40, "fx": 38, "flow": 52, "sentiment": 48, "technical": 50},
    }


class TestExpertConsensusChecks:
    def test_build_review_detects_conflicts_and_drift(self):
        snap = _conflict_snapshot()
        review = build_expert_consensus_review(snap, settings={"expert_consensus": {"mss_drift_threshold": 10}})
        assert review is not None
        assert review.conflicts
        assert review.mss_drift

    def test_checks_block_identifier(self):
        snap = _conflict_snapshot()
        snap["team_review"]["blocked"] = True
        snap["team_review"]["block_reason"] = "fake news"
        checks = run_expert_consensus_checks(snap, settings={})
        assert checks["passed"] is False
        assert checks["blocking_flags"]

    def test_evidence_maps_to_policy(self):
        checks = run_expert_consensus_checks(_conflict_snapshot(), settings={})
        evidence = expert_consensus_to_harness_evidence(checks, snapshot=_conflict_snapshot())
        assert any("专家冲突" in line for line in evidence["memory"])
        assert evidence["playbook"]


class TestExpertConsensusHarness:
    def test_refines_on_close(self, harness_tmp):
        result = apply_expert_consensus_harness_refinement(
            _conflict_snapshot(),
            settings={
                "expert_consensus": {"enabled": True, "max_mss_drift_flags": 8},
                "harness": {"enabled": True, "jobs": {"expert_consensus": True}},
            },
            workflow="close",
        )
        assert result.get("skipped") is False
        assert result.get("checks", {}).get("review")

    def test_skips_without_experts(self):
        result = apply_expert_consensus_harness_refinement(
            {"name": "test"},
            settings={"expert_consensus": {"enabled": True}},
        )
        assert result.get("skipped") is True

    def test_forge_blocks_blocked_bullish(self, harness_tmp):
        snap = _conflict_snapshot()
        snap["team_review"]["blocked"] = True
        snap["team_review"]["consensus_label"] = "可做"
        checks = run_expert_consensus_checks(snap, settings={})
        result = apply_skill_refinement(
            "expert_consensus",
            {
                "memory": ["bad consensus"],
                "summary": "consensus bad",
                "forge_domain": {
                    "review": checks["review"],
                    "expert_results": snap["expert_results"],
                    "checks": checks,
                },
                "rigor_domain": {
                    "review": checks["review"],
                    "expert_results": snap["expert_results"],
                    "checks": checks,
                },
            },
            settings={"harness": {"enabled": True, "jobs": {"expert_consensus": True}}},
        )
        assert result.get("reason") == "forge_gate_failed"

    def test_close_harness_wires_snapshot(self, harness_tmp):
        report = run_close_harness_refinements(
            verify={"name": "大盘"},
            snapshot=_conflict_snapshot(),
            settings={
                "expert_consensus": {"enabled": True, "max_mss_drift_flags": 8},
                "harness": {"enabled": True, "jobs": {"expert_consensus": True}},
            },
        )
        block = report.expert_consensus
        assert block.get("skipped") is False
        assert block.get("job") == "expert_consensus"

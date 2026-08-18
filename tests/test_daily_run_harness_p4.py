# -*- coding: utf-8
"""Tests for harness snapshots and Layer B admission."""

from pathlib import Path

import pytest

from agent_reach.daily_run.harness import HarnessState, refine_after_job, refine_after_job_llm
from agent_reach.daily_run.harness_apply_gate import (
    classify_overlay_claims,
    evaluate_layer_b_admission,
    evaluate_apply_gate,
)
from agent_reach.daily_run.harness_snapshot import (
    list_snapshots,
    restore_snapshot,
    save_pre_apply_snapshot,
)


@pytest.fixture
def harness_tmp(monkeypatch, tmp_path):
    hdir = tmp_path / "harness"
    monkeypatch.setattr("agent_reach.daily_run.harness.harness_dir", lambda: hdir)
    monkeypatch.setattr("agent_reach.daily_run.harness._state_path", lambda: hdir / "harness_state.json")
    monkeypatch.setattr("agent_reach.daily_run.harness._refinements_path", lambda: hdir / "refinements.jsonl")
    monkeypatch.setattr("agent_reach.daily_run.harness_apply_gate._audit_path", lambda: hdir / "apply_audit.jsonl")
    monkeypatch.setattr("agent_reach.daily_run.harness_snapshot.harness_dir", lambda: hdir)
    monkeypatch.setattr("agent_reach.daily_run.harness_snapshot._state_path", lambda: hdir / "harness_state.json")
    return hdir


class TestHarnessSnapshots:
    def test_save_and_restore_snapshot(self, harness_tmp):
        state = HarnessState.load()
        _, edit = state.upsert("memory", "test_mem", title="t", content="before edit", job="test")
        assert edit.action == "create"
        state.save()

        path = save_pre_apply_snapshot(state, job="close", trigger="layer_a")
        assert path and path.exists()

        state.upsert("memory", "test_mem", title="t", content="after edit", job="close")
        state.save()
        assert state.get("memory", "test_mem").content == "after edit"

        result = restore_snapshot(path)
        restored = HarnessState.load()
        assert restored.get("memory", "test_mem").content == "before edit"
        assert result["restored_from"] == str(path)

    def test_refine_writes_snapshot(self, harness_tmp):
        result = refine_after_job(
            "verify",
            evidence={"memory": ["test memory line"], "summary": "verify test"},
            settings={"harness": {"enabled": True, "snapshots": {"enabled": True}}},
        )
        assert result.get("snapshot_path")
        rows = list_snapshots(limit=5)
        assert rows


class TestLayerBAdmission:
    def test_rejects_threshold_drift(self):
        proposal = {
            "edits": [
                {
                    "action": "create",
                    "kind": "policy",
                    "content": "macro_veto→10 激进下调",
                }
            ]
        }
        admission = evaluate_layer_b_admission(proposal, settings={"harness": {"layer_b_admission": {"enabled": True}}})
        assert admission.passed is False
        assert admission.rejected_edits

    def test_accepts_safe_playbook_edit(self):
        proposal = {
            "edits": [
                {
                    "action": "create",
                    "kind": "playbook",
                    "content": "收盘后优先核对 quote 覆盖率",
                }
            ]
        }
        admission = evaluate_layer_b_admission(proposal)
        assert admission.passed is True
        assert len(admission.accepted_edits) == 1

    def test_llm_refine_skips_on_admission_fail(self, harness_tmp, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.harness.plan_harness_refinement",
            lambda *a, **k: {
                "summary": "bad",
                "edits": [{"action": "create", "kind": "policy", "content": "min_cash_ratio→0.99"}],
                "planner": "llm",
            },
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.harness.review_harness_refine",
            lambda *a, **k: {"should_refine": True, "instructions": ""},
        )
        result = refine_after_job_llm(
            "close",
            evidence={"portfolio_summary": {"daily_pnl_pct": 1.0}},
            settings={"harness": {"enabled": True, "llm_refine": {"enabled": True}}},
            skip_review=True,
        )
        assert result.get("skipped") is True
        assert result.get("reason") == "layer_b_admission_rejected"


class TestClaimClassification:
    def test_classify_overlay_claims_decisions(self):
        claims = classify_overlay_claims(
            ["正常记忆条目", "假设：明日验证 MSS", "a" * 900, "b" * 900],
            settings={"harness": {"injection": {"max_overlay_claims": 2, "max_overlay_chars": 500}}},
        )
        decisions = {c["decision"] for c in claims}
        assert "adopted" in decisions
        assert "verify" in decisions
        assert "ignored" in decisions

    def test_morning_gate_blocks_playbook(self):
        gate = evaluate_apply_gate(
            "morning",
            {"morning_gate_passed": False, "memory": ["x"], "playbook": ["激进建仓"]},
        )
        assert "playbook" in gate.blocked_kinds

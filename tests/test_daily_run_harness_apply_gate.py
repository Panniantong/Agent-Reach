# -*- coding: utf-8
"""Tests for harness apply gate and bounded injection."""

from pathlib import Path

import pytest

from agent_reach.daily_run.data_audit_harness import audit_to_harness_evidence
from agent_reach.daily_run.harness import HarnessState, refine_after_job
from agent_reach.daily_run.harness_apply_gate import (
    bound_kind_texts,
    bound_overlay_blobs,
    evaluate_apply_gate,
    load_recent_apply_audit,
    record_apply_audit,
)


@pytest.fixture
def harness_tmp(monkeypatch, tmp_path):
    hdir = tmp_path / "harness"
    monkeypatch.setattr("agent_reach.daily_run.harness.harness_dir", lambda: hdir)
    monkeypatch.setattr("agent_reach.daily_run.harness._state_path", lambda: hdir / "harness_state.json")
    monkeypatch.setattr("agent_reach.daily_run.harness._refinements_path", lambda: hdir / "refinements.jsonl")
    monkeypatch.setattr("agent_reach.daily_run.harness_apply_gate._audit_path", lambda: hdir / "apply_audit.jsonl")
    return hdir


class TestApplyGate:
    def test_blocks_policy_when_audit_fails(self, harness_tmp):
        evidence = audit_to_harness_evidence(
            {
                "passed": False,
                "issues": ["quote 过期"],
                "warnings": [],
                "structured_review_complete": True,
            }
        )
        gate = evaluate_apply_gate("data_audit", evidence, settings={"harness": {"apply_gate": {"enabled": True}}})
        assert "policy" in gate.blocked_kinds
        assert "audit_failed" in gate.verification_signals

    def test_refine_skips_policy_on_audit_fail(self, harness_tmp):
        evidence = audit_to_harness_evidence(
            {
                "passed": False,
                "issues": ["缺少数据来源 quote"],
                "warnings": ["覆盖率偏低"],
                "structured_review_complete": False,
            }
        )
        result = refine_after_job(
            "data_audit",
            evidence=evidence,
            settings={
                "harness": {
                    "enabled": True,
                    "apply_gate": {"enabled": True},
                    "injection": {"max_per_kind_per_job": 20},
                }
            },
        )
        assert result["skipped"] is False
        assert result["apply_gate"]["blocked_kinds"] == ["policy"]
        state = HarnessState.load()
        assert not state.entries["policy"]
        assert state.entries["memory"]
        assert state.entries["plan"]
        audit = load_recent_apply_audit(limit=1)
        assert audit and audit[0]["refinement_id"] == result["refinement_id"]

    def test_refine_applies_policy_when_audit_passes(self, harness_tmp):
        evidence = audit_to_harness_evidence(
            {
                "passed": True,
                "issues": ["偏差：价格变动超过锚点阈值"],
                "warnings": [],
                "structured_review_complete": True,
            }
        )
        result = refine_after_job(
            "data_audit",
            evidence=evidence,
            settings={"harness": {"enabled": True, "apply_gate": {"enabled": True}}},
        )
        state = HarnessState.load()
        assert any("block_on_price_deviation" in e.content for e in state.entries["policy"].values())
        assert result["apply_gate"]["blocked_kinds"] == []


class TestBoundedInjection:
    def test_bound_kind_texts_caps_count(self):
        texts = [f"line-{i}" for i in range(20)]
        kept, meta = bound_kind_texts(texts, settings={"harness": {"injection": {"max_per_kind_per_job": 3}}})
        assert len(kept) == 3
        assert meta["dropped_count"] == 17

    def test_bound_overlay_blobs_caps_chars(self):
        blobs = ["a" * 500, "b" * 500, "c" * 500]
        kept, meta = bound_overlay_blobs(
            blobs,
            settings={"harness": {"injection": {"max_overlay_claims": 3, "max_overlay_chars": 800}}},
        )
        assert meta["kept_count"] <= 3
        assert meta["total_chars"] <= 800
        assert len(kept) >= 1

    def test_record_apply_audit_append(self, harness_tmp):
        from agent_reach.daily_run.harness_apply_gate import ApplyGateResult

        gate = ApplyGateResult(verification_signals=["audit_failed"], blocked_kinds=["policy"])
        record_apply_audit(
            job="data_audit",
            refinement_id="refine_0001",
            gate=gate,
            injection_meta={"memory": {"dropped_count": 1}},
            skipped_kinds=["gate_blocked:policy:1"],
            changes=2,
        )
        path = Path(harness_tmp) / "apply_audit.jsonl"
        assert path.exists()
        rows = load_recent_apply_audit(limit=1)
        assert rows[0]["job"] == "data_audit"

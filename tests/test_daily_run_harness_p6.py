# -*- coding: utf-8
"""Tests for overlay claim enforcement and unified apply audit."""

import pytest

from agent_reach.daily_run.harness import refine_after_job_llm
from agent_reach.daily_run.harness_apply_gate import (
    enforce_overlay_claims,
    load_recent_apply_audit,
    record_apply_audit,
)
from agent_reach.daily_run.harness_policy import _collect_text_blobs
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement
from agent_reach.daily_run.harness_weekly_narrative import build_weekly_harness_narrative


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


class TestOverlayClaimEnforcement:
    def test_enforce_overlay_claims_excludes_verify_markers(self):
        adopted, meta = enforce_overlay_claims(
            ["正常策略条目", "假设：明日验证 MSS", "进攻期维持纪律"],
            settings={"harness": {"injection": {"enforce_claim_decisions": True}}},
        )
        assert len(adopted) == 2
        assert meta["verify_count"] == 1
        assert not any("假设" in blob for blob in adopted)

    def test_collect_text_blobs_uses_adopted_only(self, harness_tmp):
        from agent_reach.daily_run.harness import HarnessState

        state = HarnessState.load()
        state.upsert("memory", "m1", title="t", content="假设：待验证阈值", job="test")
        state.upsert("memory", "m2", title="t", content="进攻期维持仓位", job="test")
        blobs = _collect_text_blobs(
            state,
            sources={"memory"},
            kind="memory",
            settings={"harness": {"injection": {"enforce_claim_decisions": True}}},
        )
        assert len(blobs) == 1
        assert "进攻期" in blobs[0]


class TestUnifiedApplyAudit:
    def test_forge_skip_writes_audit(self, harness_tmp):
        apply_skill_refinement(
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
        rows = load_recent_apply_audit(limit=1)
        assert rows
        assert rows[0]["status"] == "skipped"
        assert rows[0]["reason"] == "forge_gate_failed"

    def test_layer_b_reject_writes_audit(self, harness_tmp, monkeypatch):
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
        refine_after_job_llm(
            "close",
            evidence={"portfolio_summary": {"daily_pnl_pct": 1.0}},
            settings={"harness": {"enabled": True, "llm_refine": {"enabled": True}}},
            skip_review=True,
        )
        rows = load_recent_apply_audit(limit=1)
        assert rows
        assert rows[0]["status"] == "skipped"
        assert rows[0]["reason"] == "layer_b_admission_rejected"
        assert rows[0]["layer"] == "b"

    def test_record_apply_audit_layer_b_success(self, harness_tmp):
        record_apply_audit(
            job="weekly",
            refinement_id="refine_0099",
            status="applied",
            layer="b",
            changes=2,
        )
        rows = load_recent_apply_audit(limit=1)
        assert rows[0]["layer"] == "b"
        assert rows[0]["status"] == "applied"

    def test_weekly_narrative_counts_forge_and_layer_b(self, harness_tmp):
        audit_path = harness_tmp / "apply_audit.jsonl"
        audit_path.write_text(
            "\n".join(
                [
                    '{"at":"2026-08-15T09:00:00+00:00","job":"pnl_target","status":"skipped","reason":"forge_gate_failed","changes":0}',
                    '{"at":"2026-08-15T10:00:00+00:00","job":"close","status":"skipped","reason":"layer_b_admission_rejected","layer":"b","changes":0}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        narrative = build_weekly_harness_narrative(
            week_start="2026-08-11",
            week_end="2026-08-17",
        )
        assert narrative["forge_blocks"] == 1
        assert narrative["layer_b_skips"] == 1

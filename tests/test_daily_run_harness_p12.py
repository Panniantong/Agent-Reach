# -*- coding: utf-8
"""Tests for finance_ledger_prep and context-doctor cross-kind conflicts."""

import pytest

from agent_reach.daily_run.finance_ledger_prep_harness import apply_finance_ledger_prep_harness_refinement
from agent_reach.daily_run.harness import load_harness, refine_after_job
from agent_reach.daily_run.harness_context_doctor import filter_cross_kind_conflicts
from agent_reach.daily_run.harness_finance import check_ledger_entry_prep, run_finance_ledger_prep_checks
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


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


GOOD_TRADES = [
    {
        "at": "2026-08-18T10:00:00+08:00",
        "trade_id": "T1",
        "actions": [
            {
                "side": "buy",
                "code": "600584",
                "shares": 100,
                "price": 80.0,
                "amount": 8000.0,
                "commission": 5.0,
                "reasoning": "MSS 偏强加仓",
                "prepared_by": "agent",
                "approved_by": "reviewer",
            }
        ],
    }
]


class TestFinanceLedgerPrep:
    def test_material_buy_missing_reasoning_flags_review(self):
        bad = [
            {
                "at": "2026-08-18T10:00:00+08:00",
                "actions": [
                    {
                        "side": "buy",
                        "code": "600584",
                        "shares": 1000,
                        "price": 80.0,
                        "amount": 80000.0,
                        "commission": 0.0,
                    }
                ],
            }
        ]
        prep = check_ledger_entry_prep(
            bad,
            settings={"finance_ledger_prep": {"materiality_cny": 5000}},
        )
        assert prep.ready_for_journal is False
        assert prep.review_flags

    def test_prep_harness_refines(self, harness_tmp):
        summary = {"as_of": "2026-08-18", "trades": GOOD_TRADES}
        result = apply_finance_ledger_prep_harness_refinement(
            summary,
            settings={
                "finance_ledger_prep": {"enabled": True},
                "harness": {"enabled": True, "jobs": {"finance_ledger_prep": True}},
            },
        )
        assert result.get("skipped") is False
        assert result.get("checks", {}).get("passed") is True

    def test_forge_blocks_bad_prep(self, harness_tmp):
        summary = {
            "as_of": "2026-08-18",
            "trades": [
                {
                    "at": "2026-08-18T10:00:00+08:00",
                    "trade_id": "DUP",
                    "actions": [{"side": "buy", "code": "600584", "shares": 1, "price": 1, "amount": 1}],
                },
                {
                    "at": "2026-08-18T11:00:00+08:00",
                    "trade_id": "DUP",
                    "actions": [{"side": "sell", "code": "600584", "shares": 1, "price": 1, "amount": 1}],
                },
            ],
        }
        checks = run_finance_ledger_prep_checks(summary)
        assert checks.get("passed") is False
        result = apply_skill_refinement(
            "finance_ledger_prep",
            {
                "memory": ["bad prep"],
                "summary": "prep bad",
                "forge_domain": {
                    "prep": checks["prep"],
                    "trades": summary["trades"],
                },
                "rigor_domain": {
                    "prep": checks["prep"],
                    "trades": summary["trades"],
                },
            },
            settings={"harness": {"enabled": True, "jobs": {"finance_ledger_prep": True}}},
        )
        assert result.get("reason") == "forge_gate_failed"


class TestContextDoctorConflicts:
    def test_blocks_aggressive_playbook_when_existing_defensive(self, harness_tmp):
        state = load_harness()
        state.upsert(
            "policy",
            "defensive",
            title="def",
            content="下周 verify 偏防御，减少 aggressive 新开仓",
            source="test",
            job="weekly",
            evidence="seed",
        )
        state.save()
        filtered, meta = filter_cross_kind_conflicts(
            {
                "memory": [],
                "policy": [],
                "playbook": ["明日适度进攻，提高 aggressive 阈值"],
                "plan": [],
            },
            state,
        )
        assert filtered["playbook"] == []
        assert meta["dropped_count"] == 1

    def test_refine_records_conflict_drops(self, harness_tmp):
        state = load_harness()
        state.upsert(
            "policy",
            "defensive",
            title="def",
            content="policy：偏防御",
            source="test",
            job="weekly",
            evidence="seed",
        )
        state.save()
        result = refine_after_job(
            "code_walk",
            evidence={
                "memory": [],
                "policy": [],
                "playbook": ["playbook：激进加仓进攻"],
                "plan": [],
                "summary": "code_walk",
            },
            settings={"harness": {"enabled": True, "jobs": {"code_walk": True}}},
        )
        conflicts = (result.get("injection") or {}).get("context_doctor_conflicts") or {}
        assert conflicts.get("dropped_count", 0) >= 1

# -*- coding: utf-8
"""Tests for finance reconcile snapshot, statements, rigor schema, context doctor."""

import pytest

from agent_reach.daily_run.finance_statements_harness import apply_finance_statements_harness_refinement
from agent_reach.daily_run.harness import load_harness, refine_after_job
from agent_reach.daily_run.harness_context_doctor import dedupe_incoming_texts, text_similarity
from agent_reach.daily_run.harness_finance import (
    analyze_reconciliation_snapshot,
    build_weekly_financial_statements,
    reconcile_close_portfolio,
    run_finance_close_checks,
)
from agent_reach.daily_run.harness_rigor_schema import validate_optimize_study_schema
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


PORTFOLIO = {
    "as_of": "2026-08-18",
    "start_total": 100000.0,
    "end_total": 100500.0,
    "daily_pnl": 500.0,
    "capital_net_flow": 0.0,
    "cash": 20000.0,
    "holdings": [{"code": "600584", "name": "长电", "shares": 1000, "price": 80.5}],
    "trades": [
        {
            "at": "2026-08-15T10:00:00+08:00",
            "actions": [
                {
                    "side": "sell",
                    "code": "600584",
                    "shares": 100,
                    "price": 80.0,
                    "amount": 8000.0,
                    "commission": 0.0,
                }
            ],
        }
    ],
}


WEEKLY = {
    "week_start": "2026-08-11",
    "week_end": "2026-08-15",
    "start_total": 100000.0,
    "end_total": 101200.0,
    "weekly_pnl": 1200.0,
    "weekly_pnl_pct": 1.2,
    "stock_pnl": 900.0,
    "cash_pnl": 300.0,
    "cash": 21000.0,
    "holdings": [{"code": "600584", "name": "长电", "shares": 1000, "week_end_price": 80.2}],
}


class TestFinanceReconcileSnapshot:
    def test_open_items_and_stale_flags(self):
        reconcile = reconcile_close_portfolio({"start_total": 100, "end_total": 200, "daily_pnl": 50})
        snapshot = analyze_reconciliation_snapshot(
            PORTFOLIO,
            reconcile,
            settings={"finance_reconcile": {"stale_days": 2, "materiality_cny": 100}},
        )
        assert snapshot.open_items
        assert any(i["category"] == "missing_cost_basis" for i in snapshot.open_items)
        assert snapshot.stale_flags
        assert snapshot.aging_buckets["1-3d"] >= 1

    def test_close_checks_include_snapshot(self):
        checks = run_finance_close_checks(PORTFOLIO)
        assert checks.get("reconcile_snapshot")
        assert checks["reconcile_snapshot"]["open_items"]


class TestFinanceStatements:
    def test_build_weekly_statements(self):
        statements = build_weekly_financial_statements(WEEKLY)
        assert statements["income_statement"]["net_income"] == 1200.0
        assert statements["balance_sheet"]["assets_total"] == 101200.0
        assert statements["reconciled"] is True

    def test_finance_statements_harness_refines(self, harness_tmp):
        result = apply_finance_statements_harness_refinement(
            WEEKLY,
            settings={
                "finance_statements": {"enabled": True},
                "harness": {"enabled": True, "jobs": {"finance_statements": True}},
            },
        )
        assert result.get("skipped") is False
        assert result.get("statements")


class TestRigorSchema:
    def test_optimize_schema_passes(self):
        schema = validate_optimize_study_schema(
            {
                "objective": "excess_return",
                "best_score": 0.12,
                "trials": 24,
                "metrics": {"total_return": 0.1, "max_drawdown": 0.05},
                "best_params": {"macro_veto": 40, "aggressive_entry": 55},
            }
        )
        assert schema.passed is True

    def test_optimize_schema_blocks_missing_metrics(self):
        schema = validate_optimize_study_schema(
            {
                "objective": "excess_return",
                "best_score": 0.12,
                "trials": 24,
                "metrics": {"total_return": 0.1},
                "best_params": {"macro_veto": 40, "aggressive_entry": 55},
            }
        )
        assert schema.passed is False
        assert any("max_drawdown" in v for v in schema.violations)

    def test_optimize_harness_blocks_bad_schema(self, harness_tmp):
        result = apply_skill_refinement(
            "optimize",
            {
                "memory": ["bad optimize"],
                "summary": "optimize bad",
                "forge_domain": {
                    "objective": "excess_return",
                    "best_score": 0.1,
                    "trials": 5,
                    "metrics": {"total_return": 0.1},
                    "best_params": {"macro_veto": 40, "aggressive_entry": 55},
                },
                "rigor_domain": {
                    "objective": "excess_return",
                    "best_score": 0.1,
                    "trials": 5,
                    "metrics": {"total_return": 0.1},
                    "best_params": {"macro_veto": 40, "aggressive_entry": 55},
                },
            },
            settings={"harness": {"enabled": True, "jobs": {"optimize": True}}},
        )
        assert result.get("reason") == "rigor_check_failed"


class TestContextDoctor:
    def test_similarity_detects_near_duplicate(self):
        assert text_similarity("finance_close 对账通过", "finance close 对账通过") >= 0.86

    def test_dedupe_drops_existing_duplicate(self):
        kept, meta = dedupe_incoming_texts(
            ["finance_close 对账通过", "全新 unique 记忆条目"],
            ["finance close 对账通过"],
        )
        assert len(kept) == 1
        assert meta["dropped_count"] == 1

    def test_refine_dedupes_against_state(self, harness_tmp):
        state = load_harness()
        state.upsert(
            "memory",
            "seed_mem",
            title="seed",
            content="finance_close 收盘对账通过",
            source="test",
            job="finance_close",
            evidence="seed",
        )
        state.save()
        result = refine_after_job(
            "finance_close",
            evidence={
                "memory": ["finance close 收盘对账通过", "新的 plan 条目"],
                "summary": "finance_close",
            },
            settings={"harness": {"enabled": True, "jobs": {"finance_close": True}}},
        )
        assert result.get("skipped") is False
        injection = result.get("injection") or {}
        doctor = injection.get("context_doctor") or {}
        assert doctor.get("memory", {}).get("dropped_count", 0) >= 1

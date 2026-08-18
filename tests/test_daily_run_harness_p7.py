# -*- coding: utf-8
"""Tests for dsh-finance and dsh-rigorquant harness ports."""

import pytest

from agent_reach.daily_run.finance_close_harness import apply_finance_close_harness_refinement
from agent_reach.daily_run.harness_finance import (
    analyze_close_variance_bridge,
    analyze_portfolio_risk,
    reconcile_close_portfolio,
    run_finance_close_checks,
)
from agent_reach.daily_run.harness_forge_gates import validate_finance_close_forge, validate_optimize_forge
from agent_reach.daily_run.harness_rigor_check import evaluate_rigor_battery, rigor_blocks_refine
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
    "holdings": [
        {
            "code": "600584",
            "name": "长电科技",
            "shares": 1000,
            "price": 80.5,
            "sector": "半导体",
        }
    ],
}


class TestHarnessFinance:
    def test_portfolio_risk_flags_concentration(self):
        risk = analyze_portfolio_risk(
            PORTFOLIO,
            settings={"finance_close": {"max_position_pct": 50, "min_cash_pct": 25}},
        )
        assert risk.largest_position
        assert any("现金" in f for f in risk.flags)

    def test_reconcile_and_variance_bridge(self):
        reconcile = reconcile_close_portfolio(PORTFOLIO)
        assert reconcile.reconciled is True
        variance = analyze_close_variance_bridge(PORTFOLIO)
        assert variance.reconciled is True
        assert variance.total_variance == 500.0

    def test_finance_close_harness_refines(self, harness_tmp):
        result = apply_finance_close_harness_refinement(
            PORTFOLIO,
            settings={
                "finance_close": {"enabled": True, "harness_evolve": True},
                "harness": {"enabled": True, "jobs": {"finance_close": True}},
            },
        )
        assert result.get("skipped") is False
        assert result.get("refinement_id")
        checks = result.get("checks") or {}
        assert checks.get("risk")
        assert checks.get("reconcile", {}).get("reconciled") is True


class TestHarnessRigor:
    def test_rigor_battery_optimize_blocks_bad_weights(self):
        rigor = evaluate_rigor_battery(
            "optimize",
            {
                "best_params": {"macro_veto": 40, "aggressive_entry": 50, "mss_weights": {"a": 0.9, "b": 0.9}},
                "best_score": 0.2,
                "trials": 10,
                "metrics": {"total_return": 0.1},
            },
        )
        assert rigor is not None
        assert rigor.passed is False
        assert rigor_blocks_refine(rigor)

    def test_finance_close_rigor_does_not_block_refine(self, harness_tmp):
        domain = run_finance_close_checks(
            {"as_of": "2026-08-18", "start_total": 100, "end_total": 200, "daily_pnl": 50},
        )
        rigor = evaluate_rigor_battery(
            "finance_close",
            {**domain, "portfolio_summary": {"as_of": "2026-08-18", "end_total": 200}},
        )
        assert rigor is not None
        assert rigor_blocks_refine(rigor) is False

    def test_optimize_forge_rejects_out_of_range(self):
        result = validate_optimize_forge({"best_params": {"macro_veto": 5, "aggressive_entry": 50}})
        assert result.passed is False

    def test_optimize_rigor_failure_skips_refine(self, harness_tmp):
        result = apply_skill_refinement(
            "optimize",
            {
                "memory": ["bad optimize"],
                "summary": "optimize bad",
                "forge_domain": {
                    "best_params": {"macro_veto": 40, "aggressive_entry": 50, "mss_weights": {"a": 0.9, "b": 0.9}},
                    "best_score": 0.2,
                    "trials": 10,
                    "metrics": {"total_return": 0.1},
                },
                "rigor_domain": {
                    "best_params": {"macro_veto": 40, "aggressive_entry": 50, "mss_weights": {"a": 0.9, "b": 0.9}},
                    "best_score": 0.2,
                    "trials": 10,
                    "metrics": {"total_return": 0.1},
                },
            },
            settings={
                "harness": {
                    "enabled": True,
                    "jobs": {"optimize": True},
                    "rigor_check": {"enabled": True, "block_on_fail": {"optimize": True}},
                }
            },
        )
        assert result.get("reason") == "rigor_check_failed"

    def test_finance_close_forge_requires_end_total(self):
        result = validate_finance_close_forge({"portfolio_summary": {"start_total": 100}})
        assert result.passed is False

# -*- coding: utf-8
"""Tests for finance_ledger journal-entry harness."""

import pytest

from agent_reach.daily_run.finance_ledger_harness import apply_finance_ledger_harness_refinement
from agent_reach.daily_run.harness_finance import check_trade_ledger_journal, run_finance_ledger_checks
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
                "name": "长电",
                "shares": 100,
                "price": 80.0,
                "amount": 8000.0,
                "commission": 5.0,
                "reasoning": "test buy",
            }
        ],
    },
    {
        "at": "2026-08-18T14:00:00+08:00",
        "trade_id": "T2",
        "actions": [
            {
                "side": "sell",
                "code": "600584",
                "name": "长电",
                "shares": 50,
                "price": 81.0,
                "amount": 4050.0,
                "commission": 3.0,
                "cost_basis": 4002.5,
                "realized_pnl": 44.5,
            }
        ],
    },
]


class TestFinanceLedgerJournal:
    def test_balanced_ledger_passes(self):
        journal = check_trade_ledger_journal(GOOD_TRADES)
        assert journal.balanced is True
        assert journal.actions_checked == 2

    def test_amount_mismatch_blocks(self):
        bad = [
            {
                "at": "2026-08-18T10:00:00+08:00",
                "actions": [
                    {
                        "side": "buy",
                        "code": "600584",
                        "shares": 100,
                        "price": 80.0,
                        "amount": 9000.0,
                        "commission": 0.0,
                    }
                ],
            }
        ]
        journal = check_trade_ledger_journal(bad)
        assert journal.balanced is False
        assert journal.blocking_flags

    def test_finance_ledger_harness_refines(self, harness_tmp):
        summary = {
            "as_of": "2026-08-18",
            "trades": GOOD_TRADES,
            "trade_cash_flow": -3998.0,
            "realized_pnl": 44.5,
        }
        result = apply_finance_ledger_harness_refinement(
            summary,
            settings={
                "finance_ledger": {"enabled": True},
                "harness": {"enabled": True, "jobs": {"finance_ledger": True}},
            },
        )
        assert result.get("skipped") is False
        assert result.get("refinement_id")
        assert result.get("checks", {}).get("passed") is True

    def test_forge_blocks_bad_journal(self, harness_tmp):
        summary = {
            "as_of": "2026-08-18",
            "trades": [
                {
                    "at": "2026-08-18T10:00:00+08:00",
                    "actions": [
                        {
                            "side": "buy",
                            "code": "600584",
                            "shares": 100,
                            "price": 80.0,
                            "amount": 9999.0,
                            "commission": 0.0,
                        }
                    ],
                }
            ],
        }
        checks = run_finance_ledger_checks(summary)
        assert checks.get("passed") is False
        result = apply_skill_refinement(
            "finance_ledger",
            {
                "memory": ["bad ledger"],
                "summary": "ledger bad",
                "forge_domain": {
                    "journal": checks["journal"],
                    "trades": summary["trades"],
                    "portfolio_summary": summary,
                },
                "rigor_domain": {
                    "journal": checks["journal"],
                    "trades": summary["trades"],
                },
            },
            settings={"harness": {"enabled": True, "jobs": {"finance_ledger": True}}},
        )
        assert result.get("reason") == "forge_gate_failed"

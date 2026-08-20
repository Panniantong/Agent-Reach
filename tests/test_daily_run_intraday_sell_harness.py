# -*- coding: utf-8
"""Tests for intraday sell / weekly friction harness refinements."""

import pytest

from agent_reach.daily_run.harness import _evidence_from_weekly
from agent_reach.daily_run.intraday_friction_harness import (
    apply_weekly_intraday_friction_harness_refinement,
)
from agent_reach.daily_run.intraday_sell_harness import (
    apply_intraday_sell_harness_refinement,
    apply_weekly_intraday_sell_harness_refinement,
    intraday_sell_whatif_to_harness_evidence,
)


@pytest.fixture
def harness_tmp(monkeypatch, tmp_path):
    hdir = tmp_path / "harness"
    monkeypatch.setattr("agent_reach.daily_run.harness.harness_dir", lambda: hdir)
    monkeypatch.setattr("agent_reach.daily_run.harness._state_path", lambda: hdir / "harness_state.json")
    monkeypatch.setattr(
        "agent_reach.daily_run.harness._refinements_path",
        lambda: hdir / "refinements.jsonl",
    )
    return hdir


class TestIntradaySellHarness:
    def test_summarize_evidence_missed_signals(self):
        evidence = intraday_sell_whatif_to_harness_evidence(
            {
                "skipped": False,
                "actual_sell_shares": 0,
                "hypothetical_sell_shares": 1400,
                "sell_share_delta": 1400,
                "missed_sell_signals": 2,
                "rows": [],
            },
            scope="weekly",
        )
        assert evidence["rigor_domain"]["scope"] == "weekly"
        assert any("错失 2 次" in line for line in evidence["memory"])
        assert any("step-up sell_ratio" in line for line in evidence["policy"])

    def test_apply_close_harness_refinement(self, harness_tmp):
        result = apply_intraday_sell_harness_refinement(
            {
                "as_of": "2026-08-19",
                "intraday_sell_whatif": {
                    "skipped": False,
                    "actual_sell_shares": 0,
                    "hypothetical_sell_shares": 700,
                    "sell_share_delta": 700,
                    "missed_sell_signals": 1,
                    "rows": [
                        {
                            "code": "000725",
                            "name": "京东方A",
                            "actual_action": "hold",
                            "evolved_action": "sell",
                        }
                    ],
                },
            },
            settings={"harness": {"enabled": True, "jobs": {"intraday_sell": True}}},
        )
        assert not result.get("skipped")
        assert result.get("refinement_id")
        assert result.get("job") == "intraday_sell"

    def test_apply_weekly_harness_refinement(self, harness_tmp):
        result = apply_weekly_intraday_sell_harness_refinement(
            {
                "week_start": "2026-08-18",
                "week_end": "2026-08-22",
                "intraday_sell_whatif": {
                    "skipped": False,
                    "scope": "weekly",
                    "actual_sell_shares": 0,
                    "hypothetical_sell_shares": 1400,
                    "sell_share_delta": 1400,
                    "missed_sell_signals": 2,
                    "rows": [],
                },
            },
            settings={
                "harness": {"enabled": True, "jobs": {"intraday_sell": True}},
                "intraday_sell_whatif": {"llm_optimize": False},
            },
        )
        assert not result.get("skipped")
        assert result.get("refinement_id")
        assert result.get("llm_optimize", {}).get("skipped") is True


class TestWeeklyIntradayFrictionHarness:
    def test_apply_weekly_friction_harness(self, harness_tmp):
        result = apply_weekly_intraday_friction_harness_refinement(
            {
                "week_start": "2026-08-18",
                "week_end": "2026-08-22",
                "intraday_friction_whatif": {
                    "skipped": False,
                    "scope": "weekly",
                    "friction_blocked_actual": 2,
                    "friction_would_pass": 1,
                    "trend_mismatch": 0,
                    "rows": [],
                },
            },
            settings={
                "harness": {"enabled": True, "jobs": {"intraday_friction": True}},
                "intraday_whatif": {"llm_optimize": False},
                "friction_model": {"llm_optimize": False},
            },
        )
        assert not result.get("skipped")
        assert result.get("refinement_id")
        assert result.get("llm_optimize", {}).get("skipped") is True


class TestWeeklyHarnessEvidenceMerge:
    def test_evidence_from_weekly_includes_intraday_blocks(self):
        memory, policy, playbook, plan, _summary = _evidence_from_weekly(
            {
                "report": {
                    "week_start": "2026-08-18",
                    "week_end": "2026-08-22",
                    "weekly_pnl": 1000.0,
                    "intraday_friction_whatif": {
                        "skipped": False,
                        "friction_blocked_actual": 2,
                        "friction_would_pass": 1,
                        "trend_mismatch": 0,
                        "rows": [],
                    },
                    "intraday_sell_whatif": {
                        "skipped": False,
                        "actual_sell_shares": 0,
                        "hypothetical_sell_shares": 700,
                        "sell_share_delta": 700,
                        "missed_sell_signals": 1,
                        "rows": [],
                    },
                }
            },
            settings={"harness": {"jobs": {"skill_closure": False}}},
        )
        joined = " ".join(memory + policy + playbook + plan)
        assert "盘中摩擦" in joined
        assert "scan replay" in joined

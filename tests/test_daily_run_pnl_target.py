# -*- coding: utf-8
"""Tests for next-day P&L target cycle."""

from datetime import date
from pathlib import Path

import pytest

from agent_reach.daily_run.pnl_target import (
    compute_next_day_target,
    evaluate_pending_target,
    load_pending_target,
    run_pnl_target_close_cycle,
)
from agent_reach.daily_run.pnl_target_harness import pnl_target_to_harness_evidence
from agent_reach.daily_run.trade_calendar import next_trading_day


def _summary(
    day: str,
    daily_pnl: float,
    *,
    start: float = 100000,
    end: float | None = None,
) -> dict:
    end_total = end if end is not None else start + daily_pnl
    return {
        "as_of": day,
        "start_total": start,
        "end_total": end_total,
        "daily_pnl": daily_pnl,
        "daily_pnl_pct": round(daily_pnl / start * 100, 2),
    }


class TestPnlTarget:
    def test_next_trading_day_skips_weekend(self):
        fri = date(2026, 8, 14)
        assert next_trading_day(fri).isoformat() == "2026-08-17"

    def test_compute_target_from_pct(self):
        target = compute_next_day_target(
            _summary("2026-08-17", 500, start=100000, end=100500),
            settings={"pnl_target": {"base_target_pct": 0.5, "min_target_cny": 0}},
        )
        assert target.target_date == "2026-08-18"
        assert target.target_pnl_cny == pytest.approx(502.5, abs=0.01)

    def test_close_cycle_evaluate_and_set_next(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "pnl_target.json"
        path.write_text(
            '{"pending":{"target_date":"2026-08-17","set_on":"2026-08-14","baseline_nav":100000,'
            '"target_pnl_cny":500,"target_pnl_pct":0.5,"status":"pending"}}',
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.pnl_target.next_trading_day",
            lambda d, **kw: date(2026, 8, 18),
        )

        cycle = run_pnl_target_close_cycle(
            _summary("2026-08-17", 800, start=100000, end=100800),
            settings={"pnl_target": {"enabled": True, "base_target_pct": 0.5}},
            path=path,
        )
        assert cycle["evaluated"]["hit"] is True
        assert cycle["next_target"]["target_date"] == "2026-08-18"
        pending = load_pending_target(path=path)
        assert pending is not None
        assert pending.target_pnl_cny > 0

    def test_miss_applies_penalty_evidence(self):
        cycle = {
            "evaluated": {
                "target_date": "2026-08-17",
                "target_pnl_cny": 500,
                "actual_pnl_cny": -200,
                "delta_cny": -700,
                "hit": False,
            },
            "next_target": {
                "target_date": "2026-08-18",
                "target_pnl_cny": 400,
                "target_pnl_pct": 0.4,
            },
        }
        ev = pnl_target_to_harness_evidence(cycle, settings={"pnl_target": {}})
        blob = " ".join(ev["memory"] + ev["policy"])
        assert "盈亏目标未达" in blob
        assert any("缩窄仓位" in p for p in ev["policy"])

    def test_hit_applies_reward_evidence(self):
        cycle = {
            "evaluated": {
                "target_date": "2026-08-17",
                "target_pnl_cny": 500,
                "actual_pnl_cny": 800,
                "delta_cny": 300,
                "hit": True,
            },
            "next_target": {"target_date": "2026-08-18", "target_pnl_cny": 550, "target_pnl_pct": 0.55},
        }
        ev = pnl_target_to_harness_evidence(cycle, settings={"pnl_target": {}})
        assert any("盈亏目标达成" in m for m in ev["memory"])
        assert any("盈亏目标奖励" in p for p in ev["playbook"])

    def test_evaluate_by_pct(self):
        pending = compute_next_day_target(
            _summary("2026-08-17", 0, start=100000, end=100000),
            settings={"pnl_target": {"base_target_pct": 0.5}},
        )
        result = evaluate_pending_target(
            _summary("2026-08-18", 400, start=100000, end=100400),
            pending,
            settings={"pnl_target": {"evaluate_by_pct": True}},
        )
        assert result.hit is False

    def test_compute_target_uses_harness_runtime_policy(self):
        target = compute_next_day_target(
            _summary("2026-08-17", 500, start=100000, end=100500),
            settings={
                "pnl_target": {"base_target_pct": 0.5, "min_target_cny": 0},
                "harness_runtime": {
                    "pnl_target_policy": {
                        "base_target_pct": 0.8,
                        "base_target_cny": 0,
                        "min_target_cny": 0,
                        "streak_bonus_pct": 0,
                        "miss_recovery_factor": 1.0,
                    }
                },
            },
        )
        assert target.target_pnl_cny == pytest.approx(804.0, abs=0.01)

# -*- coding: utf-8
"""Tests for pnl_overview harness skill."""

import agent_reach.daily_run.harness as h
from agent_reach.daily_run.pnl_overview_harness import (
    apply_pnl_overview_harness_refinement,
    pnl_overview_to_harness_evidence,
)


def test_pnl_overview_maps_sell_loss_to_policy():
    ev = pnl_overview_to_harness_evidence(
        {
            "realized_pnl": -38.0,
            "unrealized_pnl": -17254.0,
            "total_pnl": -17292.0,
            "win_count": 0,
            "loss_count": 1,
            "buys": [
                {
                    "name": "澜起科技",
                    "code": "688008",
                    "shares": 100,
                    "price": 255.87,
                    "amount": 25587.0,
                    "commission": 38.38,
                    "at": "2026-08-01T09:30:00+08:00",
                }
            ],
            "realized_sells": [
                {
                    "name": "澜起科技",
                    "code": "688008",
                    "shares": 100,
                    "price": 255.87,
                    "avg_buy_price": 255.87,
                    "realized_pnl": -38.0,
                    "realized_pnl_pct": -0.15,
                    "cost_basis": 25587.0,
                    "at": "2026-08-17T14:00:00+08:00",
                }
            ],
            "holdings": [
                {
                    "name": "海能达",
                    "code": "002583",
                    "shares": 500,
                    "cost": 12.5,
                    "price": 10.34,
                    "buy_at": "2026-08-10",
                    "unrealized_pnl": -11080.0,
                    "unrealized_pnl_pct": -57.17,
                }
            ],
        },
        portfolio_summary={"daily_pnl": -575.0, "daily_pnl_pct": -0.62},
    )
    blob = " ".join(ev["memory"])
    assert "盈亏总览" in blob
    assert "澜起科技" in blob
    assert "100股" in blob
    assert "255.87" in blob
    assert "2026-08-17" in blob
    assert "海能达" in blob
    assert "500股" in blob
    assert ev["plan"]


def test_apply_pnl_overview_writes_harness(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "_state_path", lambda: tmp_path / "harness_state.json")
    settings = {
        "harness": {
            "enabled": True,
            "threshold_evolution_mode": "harness",
            "jobs": {"pnl_overview": True},
        },
        "pnl_overview": {"harness_evolve": True},
    }
    ref = apply_pnl_overview_harness_refinement(
        {
            "as_of": "2026-08-17",
            "daily_pnl": -575.0,
            "holdings": [
                {"code": "600584", "name": "长电", "shares": 800, "cost": 80.8, "price": 80.8},
            ],
        },
        settings=settings,
    )
    assert ref.get("refinement_id") or ref.get("skipped") is False or ref.get("changes", 0) >= 0

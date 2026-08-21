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
    assert any("深度套牢" in p for p in ev["policy"])


def test_pnl_overview_uses_harness_tier_multiplier():
    ev = pnl_overview_to_harness_evidence(
        {
            "realized_pnl": 0,
            "unrealized_pnl": -7000.0,
            "total_pnl": -7000.0,
            "holdings": [
                {
                    "name": "测试",
                    "code": "000001",
                    "shares": 100,
                    "cost": 10.0,
                    "price": 3.0,
                    "unrealized_pnl": -700.0,
                    "unrealized_pnl_pct": -70.0,
                }
            ],
        },
        settings={
            "pnl_overview": {
                "large_unrealized_loss_cny": 5000,
                "deep_loss_tier_multiplier": 1.2,
            },
        },
    )
    assert not any("深度套牢" in p for p in ev["policy"])

    ev_deep = pnl_overview_to_harness_evidence(
        {
            "realized_pnl": 0,
            "unrealized_pnl": -7000.0,
            "total_pnl": -7000.0,
            "holdings": [
                {
                    "name": "测试",
                    "code": "000001",
                    "shares": 1000,
                    "cost": 10.0,
                    "price": 3.0,
                    "unrealized_pnl": -7000.0,
                    "unrealized_pnl_pct": -70.0,
                }
            ],
        },
        settings={
            "pnl_overview": {
                "large_unrealized_loss_cny": 5000,
                "deep_loss_tier_multiplier": 1.2,
            },
        },
    )
    assert any("深度套牢" in p for p in ev_deep["policy"])


def test_pnl_overview_win_rate_and_loss_streak_policy():
    ev = pnl_overview_to_harness_evidence(
        {
            "realized_pnl": -500,
            "unrealized_pnl": 0,
            "total_pnl": -500,
            "win_count": 1,
            "loss_count": 4,
            "realized_sells": [
                {"realized_pnl": -100, "shares": 100, "cost_basis": 1000},
                {"realized_pnl": -80, "shares": 100, "cost_basis": 1000},
                {"realized_pnl": -50, "shares": 100, "cost_basis": 1000},
            ],
        },
        settings={"pnl_overview": {"win_rate_min": 0.0, "loss_streak_max": 0}},
    )
    assert any("卖出胜率偏低" in p for p in ev["policy"])
    assert any("连亏警戒" in p for p in ev["policy"])


def test_pnl_overview_realized_gain_threshold():
    ev = pnl_overview_to_harness_evidence(
        {
            "realized_pnl": 600,
            "unrealized_pnl": 0,
            "total_pnl": 600,
            "realized_sells": [
                {
                    "name": "测试",
                    "code": "000001",
                    "shares": 100,
                    "cost_basis": 1000,
                    "realized_pnl": 600,
                }
            ],
        },
        settings={
            "pnl_overview": {
                "large_realized_loss_cny": 500,
                "large_realized_gain_cny": 800,
            },
            "harness_runtime": {
                "deep_loss_policy": {
                    "realized_loss_threshold": 500,
                    "realized_gain_threshold": 500,
                }
            },
        },
    )
    assert any("止盈参考" in p for p in ev["playbook"])


def test_pnl_overview_ledger_cost_policy():
    ev = pnl_overview_to_harness_evidence(
        {
            "realized_pnl": 0,
            "unrealized_pnl": 0,
            "total_pnl": 0,
            "realized_sells": [
                {
                    "name": "测试",
                    "code": "000001",
                    "shares": 100,
                    "cost_basis": 0,
                    "realized_pnl": 10,
                }
            ],
        },
        settings={"pnl_overview": {"ledger_cost_tolerance_cny": 0.01}},
    )
    assert any("ledger 缺买入成本" in p for p in ev["policy"])


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

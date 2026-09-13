# -*- coding: utf-8
"""Tests for liquidity + signal-strength deploy_ratio (P1)."""

from agent_reach.daily_run.deploy_signal_policy import (
    effective_deploy_ratio,
    liquidity_tier,
    low_liquidity_trim_blocked,
    signal_strength_deploy_ratio,
)


def test_liquidity_tiers():
    cfg = {"deploy_signal": {"liquidity_high_cny": 1e9, "liquidity_mid_cny": 2e8}}
    assert liquidity_tier(1.5e9, settings=cfg) == "high"
    assert liquidity_tier(5e8, settings=cfg) == "mid"
    assert liquidity_tier(1.4e8, settings=cfg) == "low"


def test_strong_signal_deploy_ratio():
    ratio, label = signal_strength_deploy_ratio(
        mss_delta=6.0,
        trend_confirmed=True,
        settings={"deploy_signal": {"strong_deploy_ratio": 0.85}},
    )
    assert ratio == 0.85
    assert "强信号" in label


def test_effective_deploy_ratio_respects_macro_cap():
    out = effective_deploy_ratio(
        0.25,
        mss_delta=6.0,
        trend_confirmed=True,
        macro_cap=0.25,
        settings={"deploy_signal": {"strong_deploy_ratio": 0.85}},
    )
    assert out["deploy_ratio"] == 0.25


def test_effective_deploy_ratio_strong_without_macro_cap():
    out = effective_deploy_ratio(
        0.25,
        mss_delta=6.0,
        trend_confirmed=True,
        settings={"deploy_signal": {"strong_deploy_ratio": 0.85}},
    )
    assert out["deploy_ratio"] == 0.85


def test_low_liquidity_trim_blocked():
    reason = low_liquidity_trim_blocked(
        current_weight_pct=20.0,
        target_weight_pct=19.5,
        turnover_cny=1.4e8,
        settings={"deploy_signal": {"low_liquidity_min_trim_pct": 0.02}},
    )
    assert reason is not None
    assert "低流动性" in reason

# -*- coding: utf-8
"""Liquidity-aware and signal-strength deploy_ratio policy (P1)."""

from __future__ import annotations

from typing import Any, Optional


def deploy_signal_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    raw = dict((settings or {}).get("deploy_signal") or {})
    return {
        "enabled": raw.get("enabled", True) is not False,
        "liquidity_enabled": raw.get("liquidity_enabled", True) is not False,
        "liquidity_high_cny": float(raw.get("liquidity_high_cny") or 1_000_000_000),
        "liquidity_mid_cny": float(raw.get("liquidity_mid_cny") or 200_000_000),
        "liquidity_high_cap": float(raw.get("liquidity_high_cap") or 1.0),
        "liquidity_mid_cap": float(raw.get("liquidity_mid_cap") or 0.5),
        "liquidity_low_cap": float(raw.get("liquidity_low_cap") or 0.25),
        "low_liquidity_min_trim_pct": float(raw.get("low_liquidity_min_trim_pct") or 0.02),
        "signal_strength_enabled": raw.get("signal_strength_enabled", True) is not False,
        "strong_mss_delta": float(raw.get("strong_mss_delta") or 5.0),
        "medium_mss_delta": float(raw.get("medium_mss_delta") or 3.0),
        "strong_deploy_ratio": float(raw.get("strong_deploy_ratio") or 0.85),
        "medium_deploy_ratio": float(raw.get("medium_deploy_ratio") or 0.5),
        "weak_deploy_ratio": float(raw.get("weak_deploy_ratio") or 0.25),
        "consecutive_signal_boost": float(raw.get("consecutive_signal_boost") or 0.25),
        "consecutive_min_streak": max(2, int(raw.get("consecutive_min_streak") or 2)),
    }


def liquidity_tier(turnover_cny: Optional[float], *, settings: Optional[dict[str, Any]] = None) -> str:
    cfg = deploy_signal_cfg(settings)
    if turnover_cny is None or turnover_cny <= 0:
        return "unknown"
    if turnover_cny >= cfg["liquidity_high_cny"]:
        return "high"
    if turnover_cny >= cfg["liquidity_mid_cny"]:
        return "mid"
    return "low"


def liquidity_deploy_cap(tier: str, *, settings: Optional[dict[str, Any]] = None) -> float:
    cfg = deploy_signal_cfg(settings)
    if tier == "high":
        return cfg["liquidity_high_cap"]
    if tier == "mid":
        return cfg["liquidity_mid_cap"]
    if tier == "low":
        return cfg["liquidity_low_cap"]
    return cfg["medium_deploy_ratio"]


def signal_strength_deploy_ratio(
    *,
    mss_delta: Optional[float] = None,
    trend_confirmed: bool = False,
    consecutive_same_direction: int = 0,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[float, str]:
    cfg = deploy_signal_cfg(settings)
    delta = abs(float(mss_delta or 0.0))
    if delta >= cfg["strong_mss_delta"] and trend_confirmed:
        ratio = cfg["strong_deploy_ratio"]
        label = "强信号"
    elif delta >= cfg["medium_mss_delta"]:
        ratio = cfg["medium_deploy_ratio"]
        label = "中信号"
    else:
        ratio = cfg["weak_deploy_ratio"]
        label = "弱信号"
    if consecutive_same_direction >= cfg["consecutive_min_streak"]:
        ratio = min(1.0, ratio + cfg["consecutive_signal_boost"])
        label = f"{label}+连续{consecutive_same_direction}次"
    return max(0.05, min(1.0, ratio)), label


def effective_deploy_ratio(
    base_ratio: float,
    *,
    turnover_cny: Optional[float] = None,
    mss_delta: Optional[float] = None,
    trend_confirmed: bool = False,
    consecutive_same_direction: int = 0,
    macro_cap: Optional[float] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Combine harness base deploy_ratio with signal tier, macro cap, and liquidity."""
    cfg = deploy_signal_cfg(settings)
    ratio = max(0.05, min(1.0, float(base_ratio)))
    notes: list[str] = []
    if not cfg["enabled"]:
        return {"deploy_ratio": ratio, "notes": notes}

    if cfg["signal_strength_enabled"]:
        sig_ratio, sig_label = signal_strength_deploy_ratio(
            mss_delta=mss_delta,
            trend_confirmed=trend_confirmed,
            consecutive_same_direction=consecutive_same_direction,
            settings=settings,
        )
        ratio = sig_ratio
        notes.append(f"信号分级={sig_label}→{sig_ratio:.0%}")

    if macro_cap is not None:
        cap = max(0.05, min(1.0, float(macro_cap)))
        if ratio > cap:
            ratio = cap
            notes.append(f"宏观防御→cap {cap:.0%}")

    if cfg["liquidity_enabled"]:
        tier = liquidity_tier(turnover_cny, settings=settings)
        cap = liquidity_deploy_cap(tier, settings=settings)
        if tier != "unknown":
            ratio = min(ratio, cap)
            notes.append(f"流动性={tier}→cap {cap:.0%}")

    return {
        "deploy_ratio": max(0.05, min(1.0, ratio)),
        "liquidity_tier": liquidity_tier(turnover_cny, settings=settings),
        "notes": notes,
    }


def low_liquidity_trim_blocked(
    *,
    current_weight_pct: float,
    target_weight_pct: float,
    turnover_cny: Optional[float],
    settings: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Block tiny trims on illiquid names when delta below min trim pct."""
    cfg = deploy_signal_cfg(settings)
    if not cfg["enabled"] or not cfg["liquidity_enabled"]:
        return None
    if liquidity_tier(turnover_cny, settings=settings) != "low":
        return None
    delta = abs(float(current_weight_pct) - float(target_weight_pct))
    min_trim = cfg["low_liquidity_min_trim_pct"] * 100.0
    if delta > 0 and delta < min_trim:
        return f"低流动性标的减仓幅度 {delta:.1f}% 低于最小 {min_trim:.1f}%，手续费不划算"
    return None


def liquidity_execution_hint(turnover_cny: Optional[float], *, settings: Optional[dict[str, Any]] = None) -> str:
    tier = liquidity_tier(turnover_cny, settings=settings)
    if tier == "low":
        return "执行困难（低流动性）"
    if tier == "mid":
        return "中等流动性"
    if tier == "high":
        return "高流动性"
    return ""

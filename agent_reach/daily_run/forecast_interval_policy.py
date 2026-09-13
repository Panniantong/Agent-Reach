# -*- coding: utf-8
"""ATR-based forecast interval width + accuracy-driven convergence (P0/P3)."""

from __future__ import annotations

import json
from typing import Any, Optional

from agent_reach.daily_run.forecast_quality import STOCK_WIDTH_MAX, STOCK_WIDTH_MIN, clamp_pct_band
from agent_reach.daily_run.snapshot_builder import _normalize_code
from agent_reach.daily_run.week_forecast import forecasts_dir


def forecast_interval_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    raw = dict((settings or {}).get("forecast_interval") or {})
    return {
        "enabled": raw.get("enabled", True) is not False,
        "atr_period": max(5, int(raw.get("atr_period") or 14)),
        "atr_multiplier": max(0.5, float(raw.get("atr_multiplier") or 2.0)),
        "min_width_pct": float(raw.get("min_width_pct") or STOCK_WIDTH_MIN),
        "max_width_pct": float(raw.get("max_width_pct") or STOCK_WIDTH_MAX),
        "convergence_enabled": raw.get("convergence_enabled", True) is not False,
        "convergence_high_hit_pct": float(raw.get("convergence_high_hit_pct") or 70.0),
        "convergence_low_hit_pct": float(raw.get("convergence_low_hit_pct") or 50.0),
        "convergence_tighten_factor": float(raw.get("convergence_tighten_factor") or 0.9),
        "convergence_widen_factor": float(raw.get("convergence_widen_factor") or 1.1),
        "accuracy_guard_enabled": raw.get("accuracy_guard_enabled", True) is not False,
        "accuracy_degrade_threshold_pct": float(raw.get("accuracy_degrade_threshold_pct") or 50.0),
        "accuracy_degrade_widen_factor": float(raw.get("accuracy_degrade_widen_factor") or 1.2),
        "accuracy_calibrate_threshold_pct": float(raw.get("accuracy_calibrate_threshold_pct") or 60.0),
        "accuracy_calibrate_weeks": max(2, int(raw.get("accuracy_calibrate_weeks") or 2)),
    }


def recent_weekly_symbol_hit_rates(*, weeks: int = 3) -> list[float]:
    rates: list[float] = []
    root = forecasts_dir()
    if not root.exists():
        return rates
    paths = sorted(
        [p for p in root.glob("20*.json") if p.name not in {"calibration.json", "tracking.json"}],
        reverse=True,
    )[:weeks]
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        reviews = list(data.get("reviews") or [])
        if not reviews:
            continue
        evals = [
            ev
            for ev in (reviews[-1].get("symbol_evals") or [])
            if ev.get("hit") is not None
        ]
        if len(evals) < 2:
            continue
        hits = sum(1 for ev in evals if ev.get("hit"))
        rates.append(round(hits / len(evals) * 100.0, 1))
    return rates


def interval_width_scale(settings: Optional[dict[str, Any]] = None) -> tuple[float, list[str]]:
    """Return multiplier for pct band width and human-readable notes."""
    cfg = forecast_interval_cfg(settings)
    scale = 1.0
    notes: list[str] = []
    rates = recent_weekly_symbol_hit_rates(weeks=3)
    if cfg["convergence_enabled"] and len(rates) >= 2:
        if all(r > cfg["convergence_high_hit_pct"] for r in rates[-2:]):
            scale *= cfg["convergence_tighten_factor"]
            notes.append(f"近{len(rates[-2:])}周命中率>{cfg['convergence_high_hit_pct']:.0f}%，区间收敛")
        elif all(r < cfg["convergence_low_hit_pct"] for r in rates[-2:]):
            scale *= cfg["convergence_widen_factor"]
            notes.append(f"近{len(rates[-2:])}周命中率<{cfg['convergence_low_hit_pct']:.0f}%，区间放宽")
    if cfg["accuracy_guard_enabled"] and rates:
        latest = rates[0]
        if latest < cfg["accuracy_degrade_threshold_pct"]:
            scale *= cfg["accuracy_degrade_widen_factor"]
            notes.append(f"最新周命中率{latest:.0f}%<{cfg['accuracy_degrade_threshold_pct']:.0f}%，降级放宽")
    return scale, notes


def should_trigger_forecast_calibrate(settings: Optional[dict[str, Any]] = None) -> bool:
    cfg = forecast_interval_cfg(settings)
    if not cfg["accuracy_guard_enabled"]:
        return False
    rates = recent_weekly_symbol_hit_rates(weeks=max(cfg["accuracy_calibrate_weeks"], 2))
    need = int(cfg["accuracy_calibrate_weeks"])
    if len(rates) < need:
        return False
    return all(r < cfg["accuracy_calibrate_threshold_pct"] for r in rates[:need])


def fetch_symbol_atr(
    code: str,
    *,
    period: int = 14,
    settings: Optional[dict[str, Any]] = None,
) -> Optional[float]:
    cfg = forecast_interval_cfg(settings)
    if not cfg["enabled"]:
        return None
    try:
        from agent_reach.daily_run.xueqiu_technicals import compute_atr_from_code

        return compute_atr_from_code(code, period=period or cfg["atr_period"])
    except Exception:
        return None


def atr_pct_band(
    *,
    base_price: float,
    mid_pct: float,
    atr: float,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[float, float, float, dict[str, Any]]:
    """Build lo/hi pct band from ATR price width centered on mid_pct."""
    cfg = forecast_interval_cfg(settings)
    if base_price <= 0 or atr <= 0:
        raise ValueError("invalid base or atr")
    half_width_pct = (cfg["atr_multiplier"] * atr / base_price) * 100.0
    scale, notes = interval_width_scale(settings)
    half_width_pct *= scale
    min_w = cfg["min_width_pct"] * scale
    max_w = cfg["max_width_pct"] * scale
    lo = mid_pct - half_width_pct
    hi = mid_pct + half_width_pct
    lo, hi, width_pts = clamp_pct_band(
        lo,
        hi,
        mid=mid_pct,
        min_width=min_w,
        max_width=max_w,
    )
    meta = {
        "atr": round(atr, 4),
        "atr_multiplier": cfg["atr_multiplier"],
        "width_scale": round(scale, 3),
        "notes": notes,
        "method": "atr",
    }
    return lo, hi, width_pts, meta


def apply_symbol_interval_policy(
    *,
    lo: float,
    hi: float,
    mid: float,
    base_price: float,
    code: str,
    enriched: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[float, float, float, dict[str, Any]]:
    """Prefer ATR band; fall back to scaled fixed pct clamp."""
    cfg = forecast_interval_cfg(settings)
    meta: dict[str, Any] = {"method": "fixed_pct"}
    atr = _optional_float((enriched or {}).get("atr14"))
    if atr is None and cfg["enabled"]:
        atr = fetch_symbol_atr(_normalize_code(code), period=cfg["atr_period"], settings=settings)
    if atr is not None and base_price > 0:
        try:
            return atr_pct_band(
                base_price=base_price,
                mid_pct=mid,
                atr=float(atr),
                settings=settings,
            )
        except ValueError:
            pass
    scale, notes = interval_width_scale(settings)
    min_w = cfg["min_width_pct"] * scale
    max_w = cfg["max_width_pct"] * scale
    lo2, hi2, width_pts = clamp_pct_band(
        lo,
        hi,
        mid=mid,
        min_width=min_w,
        max_width=max_w,
    )
    meta.update({"width_scale": round(scale, 3), "notes": notes})
    return lo2, hi2, width_pts, meta


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

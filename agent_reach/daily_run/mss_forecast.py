# -*- coding: utf-8
"""Simple MSS range forecast (Monte Carlo lite)."""

from __future__ import annotations

import random
from typing import Any, Optional


def forecast_mss_range(
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    *,
    simulations: int = 200,
) -> tuple[list[float], dict[str, Any]]:
    """
    Estimate intraday MSS range from current breakdown + volatility hints.

    Returns ([low, high], meta dict).
    """
    cfg = settings.get("mss_forecast", {})
    sims = int(cfg.get("simulations", simulations))
    breakdown = snapshot.get("mss_breakdown") or {}
    weights = settings.get("mss_weights", {})

    base = snapshot.get("mss_final")
    if base is None:
        from agent_reach.daily_run.verdict import compute_mss

        base = compute_mss(breakdown, settings)
    base = float(base)

    from agent_reach.daily_run.harness_policy import forecast_int_default

    vol_hint = _volatility_hint(snapshot)
    spread = float(forecast_int_default(settings, "base_spread")) + vol_hint * float(
        forecast_int_default(settings, "vol_multiplier")
    )

    rng = random.Random(int(base * 100) % 9973)
    samples: list[float] = []
    for _ in range(sims):
        noise = rng.gauss(0, spread / 2)
        factor_noise = sum(
            rng.gauss(0, 3) * float(weights.get(k, 0.25))
            for k in weights
            if k in breakdown
        )
        samples.append(max(0.0, min(100.0, base + noise + factor_noise)))

    samples.sort()
    lo = round(samples[int(sims * 0.15)], 1)
    hi = round(samples[int(sims * 0.85)], 1)
    if lo > hi:
        lo, hi = hi, lo

    meta = {
        "method": "monte_carlo_lite",
        "simulations": sims,
        "base_mss": base,
        "volatility_hint": vol_hint,
        "median": round(samples[sims // 2], 1),
    }
    return [lo, hi], meta


def _volatility_hint(snapshot: dict[str, Any]) -> float:
    change = snapshot.get("change_pct")
    if change is not None:
        return min(3.0, abs(float(change)) / 2)
    scans = snapshot.get("mss_intraday_actual") or []
    if len(scans) >= 2:
        return min(3.0, abs(float(scans[-1]) - float(scans[-2])) / 5)
    return 1.0

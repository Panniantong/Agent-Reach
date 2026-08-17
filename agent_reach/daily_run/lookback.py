# -*- coding: utf-8 -*-
"""Weighted lookback MSS from recent intraday scans (S_n, S_n-1, S_n-2)."""

from __future__ import annotations

from typing import Any


def compute_lookback_mss(
    scans: list[dict[str, Any]],
    settings: dict[str, Any],
) -> tuple[float, list[dict[str, Any]]]:
    """
    Weighted MSS from the last up-to-3 scans (newest first).

    Default weights: 50% / 30% / 20% for S_n, S_n-1, S_n-2.
    Partial weights are re-normalized when fewer than 3 scans exist.
    """
    if not scans:
        return 0.0, []

    from agent_reach.daily_run.harness_policy import lookback_weights_default

    weights = lookback_weights_default(settings)
    recent = list(reversed(scans[-3:]))  # newest → oldest
    used = weights[: len(recent)]
    total_w = sum(used)
    if total_w <= 0:
        return float(recent[0].get("mss_final", 0)), []

    norm = [w / total_w for w in used]
    contributions: list[dict[str, Any]] = []
    final = 0.0
    for scan, weight in zip(recent, norm):
        mss = float(scan.get("mss_final", 0))
        final += mss * weight
        contributions.append(
            {
                "scan_id": scan.get("scan_id"),
                "as_of": scan.get("as_of"),
                "mss_final": mss,
                "weight": round(weight, 4),
                "weighted": round(mss * weight, 2),
            }
        )

    return round(final, 2), contributions


def detect_mss_trend(scans: list[dict[str, Any]], *, min_points: int = 2) -> str:
    """Simple trend label from recent scan MSS values."""
    if len(scans) < min_points:
        return "insufficient"

    values = [float(s.get("mss_final", 0)) for s in scans[-3:]]
    if len(values) >= 3:
        d1 = values[-1] - values[-2]
        d2 = values[-2] - values[-3]
        if d1 > 1 and d2 > 0:
            return "turning_up"
        if d1 < -1 and d2 < 0:
            return "turning_down"
        if all(values[i] >= values[i - 1] for i in range(1, len(values))):
            return "rising"
        if all(values[i] <= values[i - 1] for i in range(1, len(values))):
            return "falling"
        return "mixed"

    delta = values[-1] - values[-2]
    if delta > 1:
        return "rising"
    if delta < -1:
        return "falling"
    return "flat"

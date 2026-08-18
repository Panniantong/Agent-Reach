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


def detect_mss_trend(
    scans: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
    *,
    min_points: int | None = None,
) -> str:
    """Simple trend label from recent scan MSS values."""
    from agent_reach.daily_run.intraday_policy import detect_mss_trend as _detect

    return _detect(scans, settings, min_points=min_points)

# -*- coding: utf-8
"""Fuse a-stock-review emotion grade into MSS macro breakdown."""

from __future__ import annotations

from typing import Any, Optional


def emotion_mss_fusion_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    mr = (settings or {}).get("market_review") or {}
    if mr.get("emotion_mss_fusion_enabled") is False:
        return False
    return mr.get("enabled", True) is not False


def emotion_mss_deltas(
    emotion: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, float]:
    """Map emotion score/rating to MSS factor adjustments."""
    mr = (settings or {}).get("market_review") or {}
    score = int(emotion.get("score") or 0)
    rating = str(emotion.get("rating") or "中")

    strong_global = float(mr.get("emotion_fusion_strong_global", 4.0))
    strong_sentiment = float(mr.get("emotion_fusion_strong_sentiment", 3.0))
    weak_global = float(mr.get("emotion_fusion_weak_global", -4.0))
    weak_sentiment = float(mr.get("emotion_fusion_weak_sentiment", -3.0))
    neutral_global = float(mr.get("emotion_fusion_neutral_global", 1.0))

    if score >= 4 or rating == "强":
        return {"global": strong_global, "sentiment": strong_sentiment}
    if score <= 0 or rating == "弱":
        return {"global": weak_global, "sentiment": weak_sentiment}
    return {"global": neutral_global, "sentiment": 0.0}


def apply_emotion_to_mss_breakdown(
    breakdown: dict[str, Any],
    emotion: Optional[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not emotion or not emotion_mss_fusion_enabled(settings):
        return dict(breakdown or {})

    from agent_reach.daily_run.macro_collector import _clamp

    deltas = emotion_mss_deltas(emotion, settings=settings)
    out = dict(breakdown or {})
    for key, delta in deltas.items():
        if key.startswith("_"):
            continue
        if key in out:
            out[key] = round(_clamp(float(out[key]) + delta), 1)
        elif delta:
            out[key] = round(_clamp(50.0 + delta), 1)

    out["_emotion_fusion_ref"] = {
        "score": emotion.get("score"),
        "rating": emotion.get("rating"),
        "position": emotion.get("position"),
        "deltas": deltas,
    }
    return out


def format_emotion_fusion_line(breakdown: dict[str, Any]) -> str:
    ref = breakdown.get("_emotion_fusion_ref") or {}
    if not ref:
        return ""
    rating = ref.get("rating") or "—"
    score = ref.get("score")
    deltas = ref.get("deltas") or {}
    parts = [f"{k}{delta:+.0f}" for k, delta in deltas.items() if delta]
    delta_s = " · ".join(parts) if parts else "—"
    return f"情绪融合（{rating}/{score}）：{delta_s}"

# -*- coding: utf-8
"""Parallel emotion grade vs MSS macro display for close cards."""

from __future__ import annotations

from typing import Any, Optional


def render_emotion_mss_parallel_markdown(
    review: dict[str, Any],
    *,
    snapshot: Optional[dict[str, Any]] = None,
) -> str:
    emotion = review.get("emotion") or {}
    if not emotion:
        return ""

    snap = snapshot or {}
    breakdown = dict(snap.get("mss_breakdown") or {})
    rating = emotion.get("rating") or "—"
    score = emotion.get("score", "—")
    position = emotion.get("position") or "—"
    global_score = breakdown.get("global")
    sentiment_score = breakdown.get("sentiment")
    mss_final = snap.get("mss_final")

    lines = [
        "### ⚖️ 情绪定级 × MSS",
        f"- **市场宽度情绪：** {rating} · 综合 **{score} 分** · 建议仓位 **{position}**",
    ]
    if global_score is not None or sentiment_score is not None:
        g_s = f"{float(global_score):.1f}" if global_score is not None else "—"
        s_s = f"{float(sentiment_score):.1f}" if sentiment_score is not None else "—"
        mss_s = f" · MSS 总分 **{float(mss_final):.1f}**" if mss_final is not None else ""
        lines.append(f"- **MSS 宏观因子：** global {g_s} · sentiment {s_s}{mss_s}")

    from agent_reach.daily_run.emotion_mss_fusion import format_emotion_fusion_line

    fusion = format_emotion_fusion_line(breakdown)
    if fusion:
        lines.append(f"- **融合调整：** {fusion.replace('情绪融合（', '').rstrip('）')}")

    return "\n".join(lines)

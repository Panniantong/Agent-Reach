# -*- coding: utf-8
"""Daily close P&L factor attribution (BacktestAttributor-style)."""

from __future__ import annotations

from typing import Any, Optional


def build_close_pnl_attribution(
    summary: dict[str, Any],
    *,
    snapshot: Optional[dict[str, Any]] = None,
    baseline: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Decompose daily portfolio P&L into held / realized / rebalance (+ MSS context)."""
    daily_pnl = summary.get("daily_pnl")
    holdings = list(summary.get("holdings") or [])
    held_day = round(
        sum(float(h.get("day_pnl") or 0) for h in holdings if h.get("day_pnl") is not None),
        2,
    )
    has_held = any(h.get("day_pnl") is not None for h in holdings)
    realized = round(float(summary.get("realized_pnl") or 0), 2)
    cash_pnl = summary.get("cash_pnl")
    stock_pnl = summary.get("stock_pnl")

    rebalance: Optional[float] = None
    if daily_pnl is not None:
        rebalance = round(float(daily_pnl) - (held_day if has_held else 0) - realized, 2)

    snap = snapshot or {}
    base = baseline or {}
    mss_close = float(snap.get("mss_final") or 0)
    mss_open = base.get("mss_final")
    if mss_open is None:
        morning = base.get("morning_mss") or base.get("mss_breakdown")
        if isinstance(morning, (int, float)):
            mss_open = float(morning)
    mss_delta: Optional[float] = None
    if mss_open is not None and mss_close:
        mss_delta = round(mss_close - float(mss_open), 2)

    breakdown = dict(snap.get("mss_breakdown") or {})
    emotion_ref = breakdown.get("_emotion_fusion_ref") or {}
    out: dict[str, Any] = {
        "daily_pnl": daily_pnl,
        "held_day_pnl": held_day if has_held else None,
        "realized_pnl": realized,
        "rebalance_pnl": rebalance,
        "cash_pnl": cash_pnl,
        "stock_pnl": stock_pnl,
        "capital_net_flow": summary.get("capital_net_flow"),
        "mss_delta": mss_delta,
        "mss_close": mss_close or None,
        "mss_open": float(mss_open) if mss_open is not None else None,
        "emotion_rating": emotion_ref.get("rating"),
        "emotion_score": emotion_ref.get("score"),
    }
    return out


def render_close_pnl_attribution_markdown(attr: dict[str, Any]) -> str:
    if attr.get("daily_pnl") is None and attr.get("held_day_pnl") is None:
        return ""

    lines = ["**盈亏因子分解**"]
    daily = attr.get("daily_pnl")
    if daily is not None:
        sign = "+" if float(daily) >= 0 else ""
        lines.append(f"- 当日组合 {sign}¥{float(daily):,.0f}")

    held = attr.get("held_day_pnl")
    if held is not None:
        lines.append(f"- 现持仓价格 {float(held):+,.0f}")
    realized = attr.get("realized_pnl")
    if realized is not None and abs(float(realized)) >= 0.01:
        lines.append(f"- 已清仓/成交 {float(realized):+,.0f}")
    rebalance = attr.get("rebalance_pnl")
    if rebalance is not None:
        lines.append(f"- 换仓及其它 {float(rebalance):+,.0f}")

    mss_delta = attr.get("mss_delta")
    if mss_delta is not None:
        lines.append(f"- MSS 变化 {float(mss_delta):+.1f}（{attr.get('mss_open')}→{attr.get('mss_close')}）")

    rating = attr.get("emotion_rating")
    if rating:
        score = attr.get("emotion_score")
        lines.append(f"- 市场宽度情绪 {rating}（{score} 分）")

    return "\n".join(lines)

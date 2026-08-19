# -*- coding: utf-8
"""Built-in technical expert — MA / position / volume."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.plugins.base import ExpertPlugin, PluginContext, PluginResult


class TechnicalExpert(ExpertPlugin):
    name = "technical"
    description = "技术分析派：均线、20日位置、量比"

    def run(self, context: PluginContext) -> PluginResult:
        snap = context.snapshot
        from agent_reach.daily_run.harness_policy import threshold_default

        price = _f(snap.get("price"))
        ma20 = _f(snap.get("ma20"))
        pos = _f(snap.get("position_20d"))
        vol = _f(snap.get("volume_ratio"))

        if price is None or ma20 is None:
            change = _f(snap.get("change_pct"))
            unrealized = _f(snap.get("unrealized_pnl"))
            score = 50.0
            notes: list[str] = []
            if change is not None:
                if change > 2:
                    score += 12
                    notes.append(f"涨幅 {change:+.2f}%")
                elif change < -2:
                    score -= 12
                    notes.append(f"跌幅 {change:+.2f}%")
                else:
                    notes.append(f"涨跌幅 {change:+.2f}%")
            elif price is not None:
                score = 48.0
                notes.append(f"现价 {price:.2f}（缺 MA20）")
            if unrealized is not None:
                if unrealized > 0:
                    score += 3
                elif unrealized < 0:
                    score -= 3
            score = max(0.0, min(100.0, score))
            return PluginResult(
                name=self.name,
                score=round(score, 1),
                summary="；".join(notes) or "缺少 price/ma20，技术面降级为中性",
                success=False,
            )

        score = 50.0
        notes: list[str] = []

        if price > ma20:
            score += 15
            notes.append("收盘>MA20")
        else:
            score -= 15
            notes.append("收盘<MA20")

        high_pos = float(threshold_default(context.settings, "high_position_20d"))
        if pos is not None:
            if 0.4 <= pos <= 0.6:
                score += 10
                notes.append(f"20日位置 {pos:.0%} 合理")
            elif pos > high_pos:
                score -= 10
                notes.append(f"20日位置 {pos:.0%} 偏高")

        min_vol = float(threshold_default(context.settings, "min_volume_ratio"))
        if vol is not None:
            if vol >= min_vol:
                score += 5
                notes.append(f"量比 {vol:.2f}")
            else:
                score -= 5
                notes.append(f"量比 {vol:.2f} 偏弱")

        score, kronos_notes = _apply_kronos_adjustment(
            snap, score, price, ma20, context.settings
        )
        notes.extend(kronos_notes)

        score = max(0.0, min(100.0, score))
        return PluginResult(
            name=self.name,
            score=round(score, 1),
            summary="；".join(notes) or f"技术评分 {score:.0f}",
            details={
                "price": price,
                "ma20": ma20,
                "position_20d": pos,
                "volume_ratio": vol,
                "kronos": snap.get("kronos"),
            },
        )


def _apply_kronos_adjustment(
    snap: dict[str, Any],
    score: float,
    price: Optional[float],
    ma20: Optional[float],
    settings: dict[str, Any],
) -> tuple[float, list[str]]:
    """Blend Kronos 5-day direction; cap influence per FaceCat-Kronos skill (≤15 pts)."""
    from agent_reach.daily_run.kronos_predictor import kronos_cfg

    cfg = kronos_cfg(settings)
    if not cfg.get("enabled", False):
        return score, []

    kronos = snap.get("kronos") or {}
    if not kronos.get("available"):
        return score, []

    max_delta = float(cfg.get("technical_max_score_delta", 12))
    notes: list[str] = []
    direction = str(kronos.get("direction_nd") or "flat")
    cum = kronos.get("cum_change_pct")

    if price is not None and ma20 is not None:
        ma_bull = price > ma20
        if direction == "down" and ma_bull:
            score -= max_delta
            notes.append(f"Kronos {cum:+.1f}% 看跌 vs MA20 多头")
        elif direction == "up" and not ma_bull:
            score += max_delta * 0.6
            notes.append(f"Kronos {cum:+.1f}% 看涨 vs MA20 空头")
        elif direction == "up" and ma_bull:
            score += max_delta * 0.4
            notes.append(f"Kronos 共振看涨 {cum:+.1f}%")
        elif direction == "down" and not ma_bull:
            score -= max_delta * 0.4
            notes.append(f"Kronos 共振看跌 {cum:+.1f}%")
    elif cum is not None:
        if float(cum) > 1.5:
            score += max_delta * 0.3
            notes.append(f"Kronos 5日 +{cum:.1f}%")
        elif float(cum) < -1.5:
            score -= max_delta * 0.3
            notes.append(f"Kronos 5日 {cum:.1f}%")

    return score, notes


def _f(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

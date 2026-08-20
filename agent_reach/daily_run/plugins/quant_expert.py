# -*- coding: utf-8
"""量化模型师 — 资金流、因子、量价配合."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.plugins.base import ExpertPlugin, PluginContext, PluginResult


class QuantExpert(ExpertPlugin):
    name = "quant"
    description = "量化模型师：资金流、因子、量价共振"

    def run(self, context: PluginContext) -> PluginResult:
        snap = context.snapshot
        breakdown = snap.get("mss_breakdown") or {}
        flow = float(breakdown.get("flow", 50))
        fx = float(breakdown.get("fx", 50))
        vol = _f(snap.get("volume_ratio"))
        change = _f(snap.get("change_pct"))
        from agent_reach.daily_run.harness_policy import macro_factor_baseline_default

        neutral = macro_factor_baseline_default(context.settings)
        score = flow * 0.45 + fx * 0.25 + neutral * 0.3
        notes: list[str] = [f"资金流因子 {flow:.0f}"]

        if vol is not None:
            vol_delta = max(-6.0, min(6.0, (vol - 1.0) * 8))
            score += vol_delta
            if vol >= 1.2:
                notes.append(f"量比 {vol:.2f} 放量")
            elif vol < 0.8:
                notes.append(f"量比 {vol:.2f} 缩量")
            else:
                notes.append(f"量比 {vol:.2f}")

        if change is not None:
            ch_delta = max(-8.0, min(8.0, change * 2.5))
            score += ch_delta
            notes.append(f"日内 {change:+.2f}%")

        score = max(0.0, min(100.0, score))
        return PluginResult(
            name=self.name,
            score=round(score, 1),
            summary="；".join(notes),
            details={"flow": flow, "volume_ratio": vol},
        )


def _f(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

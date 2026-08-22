# -*- coding: utf-8
"""基本面大师 — 估值、护城河、业绩质量."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.plugins.base import ExpertPlugin, PluginContext, PluginResult


class FundamentalExpert(ExpertPlugin):
    name = "fundamental"
    description = "基本面大师：财务、估值、护城河"

    def run(self, context: PluginContext) -> PluginResult:
        snap = context.snapshot
        bf = context.settings.get("buffett_filter", {})
        min_margin = float(bf.get("min_gross_margin", 0.35))
        max_peg = float(bf.get("max_peg", 1.2))
        min_roe = float(bf.get("min_roe", 0.15))

        gross_margin = _f(snap.get("gross_margin"))
        peg = _f(snap.get("peg"))
        roe = _f(snap.get("roe"))

        score = 55.0
        notes: list[str] = []
        passed = 0
        total = 0

        if gross_margin is not None:
            total += 1
            if gross_margin >= min_margin:
                score += 15
                passed += 1
                notes.append(f"毛利率 {gross_margin:.0%} ≥ {min_margin:.0%}")
            else:
                score -= 10
                notes.append(f"毛利率 {gross_margin:.0%} 低于护城河线")

        if peg is not None:
            total += 1
            if peg < max_peg:
                score += 15
                passed += 1
                notes.append(f"PEG {peg:.2f} < {max_peg}")
            else:
                score -= 10
                notes.append(f"PEG {peg:.2f} 偏高")

        if roe is not None:
            total += 1
            if roe >= min_roe:
                score += 10
                passed += 1
                notes.append(f"ROE {roe:.0%} ≥ {min_roe:.0%}")
            else:
                score -= 5
                notes.append(f"ROE {roe:.0%} 偏弱")

        pe_ttm = _f(snap.get("pe_ttm"))
        if pe_ttm is not None:
            total += 1
            if pe_ttm <= 35:
                score += 8
                passed += 1
                notes.append(f"PE(TTM) {pe_ttm:.1f}")
            elif pe_ttm >= 60:
                score -= 8
                notes.append(f"PE(TTM) {pe_ttm:.1f} 偏高")
            else:
                notes.append(f"PE(TTM) {pe_ttm:.1f}")

        turnover = snap.get("turnover_rate")
        if turnover is not None:
            from agent_reach.daily_run.valuation_metrics import format_turnover_rate

            turnover_s = format_turnover_rate(turnover)
            if turnover_s:
                notes.append(f"换手率 {turnover_s}")

        market_cap = snap.get("market_capital")
        if market_cap is not None:
            from agent_reach.daily_run.valuation_metrics import format_market_cap

            cap_s = format_market_cap(market_cap)
            if cap_s:
                notes.append(f"市值 {cap_s}")

        if total == 0:
            # Infer from holdings quality tags or neutral
            holdings = (snap.get("portfolio") or {}).get("holdings") or []
            if holdings:
                notes.append(f"持仓 {len(holdings)} 只，待补充财报字段")
            score = 58.0
            notes.append("基本面数据不完整，中性偏多（龙头持仓假设）")

        score = max(0.0, min(100.0, score))
        return PluginResult(
            name=self.name,
            score=round(score, 1),
            summary="；".join(notes) or f"基本面评分 {score:.0f}",
            details={"filters_passed": passed, "filters_total": total},
        )


def _f(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

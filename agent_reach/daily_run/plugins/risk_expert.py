# -*- coding: utf-8
"""风险控制官 — 仓位、止损、下行风险."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.plugins.base import ExpertPlugin, PluginContext, PluginResult


class RiskExpert(ExpertPlugin):
    name = "risk"
    description = "风险控制官：仓位、止损、宏观否决"

    def run(self, context: PluginContext) -> PluginResult:
        snap = context.snapshot
        settings = context.settings
        thresholds = settings.get("thresholds", {})
        trading = settings.get("trading", {})
        from agent_reach.daily_run.harness_policy import min_cash_ratio_default, runtime_float_default, threshold_default

        macro_veto = float(thresholds.get("macro_veto", threshold_default(settings, "macro_veto")))
        min_cash = float(thresholds.get("min_cash_ratio", min_cash_ratio_default(settings)))

        breakdown = snap.get("mss_breakdown") or {}
        mss = snap.get("mss_final")
        if mss is None:
            weights = context.settings.get("mss_weights", {})
            total = sum(float(breakdown.get(k, 50)) * float(weights.get(k, 0.25)) for k in weights)
            mss = total

        portfolio = snap.get("portfolio") or {}
        cash_ratio = _f(portfolio.get("cash_ratio"))
        code = str(snap.get("code") or "")
        holdings = portfolio.get("holdings") or []
        symbol_weight = None
        total = _f(portfolio.get("total"))
        for h in holdings:
            if str(h.get("code", "")).zfill(6)[-6:] == code.zfill(6)[-6:]:
                price = _f(h.get("price")) or _f(snap.get("price"))
                shares = _f(h.get("shares"))
                if price is not None and shares is not None and total:
                    symbol_weight = (price * shares) / total
                break

        score = 60.0
        notes: list[str] = []
        flags: list[str] = []

        if float(mss) < macro_veto:
            score -= 25
            flags.append("macro_veto")
            notes.append(f"MSS {float(mss):.0f} 触发宏观一票否决")

        if cash_ratio is not None:
            if cash_ratio >= min_cash:
                score += 10
                notes.append(f"现金 {cash_ratio:.0%} ≥ {min_cash:.0%}")
            else:
                score -= 15
                flags.append("low_cash")
                notes.append(f"现金 {cash_ratio:.0%} 低于风控线")

        if symbol_weight is not None:
            if symbol_weight > 0.35:
                score -= 8
                notes.append(f"单票仓位 {symbol_weight:.0%} 偏高")
            elif symbol_weight < 0.1:
                score += 3
                notes.append(f"单票仓位 {symbol_weight:.0%} 较轻")

        price = _f(snap.get("price"))
        ma20 = _f(snap.get("ma20"))
        if price is not None and ma20 is not None:
            stop_pct = runtime_float_default(settings, "trading", "stop_loss_ma20_pct")
            stop = min(ma20, price * (1 - stop_pct))
            if price < ma20:
                score -= 10
                notes.append(f"跌破 MA20，止损参考 {stop:.2f}")
            else:
                notes.append(f"MA20 上方，止损 {stop:.2f}")

        score = max(0.0, min(100.0, score))
        return PluginResult(
            name=self.name,
            score=round(score, 1),
            summary="；".join(notes) or f"风控评分 {score:.0f}",
            details={"flags": flags, "cash_ratio": cash_ratio},
        )


def _f(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

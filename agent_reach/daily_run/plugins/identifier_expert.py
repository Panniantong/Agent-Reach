# -*- coding: utf-8
"""专家鉴别 Agent — 身份、标的、价格锚点一致性."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.plugins.base import ExpertPlugin, PluginContext, PluginResult


class IdentifierExpert(ExpertPlugin):
    name = "identifier"
    description = "专家鉴别Agent：标的身份、价格锚点偏差校验"

    def run(self, context: PluginContext) -> PluginResult:
        snap = context.snapshot
        settings = context.settings
        from agent_reach.daily_run.harness_policy import threshold_default

        max_dev = float(threshold_default(settings, "max_price_deviation_pct"))

        code = snap.get("code")
        name = snap.get("name")
        price = _f(snap.get("price"))
        ref = _f(snap.get("reference_price")) or price

        issues: list[str] = []
        score = 85.0

        if not code:
            issues.append("缺少 code")
            score -= 20
        if not name:
            issues.append("缺少 name")
            score -= 10

        if price is not None and ref is not None and ref > 0:
            dev = abs(price - ref) / ref
            if dev > max_dev:
                issues.append(f"价格锚点偏差 {dev:.1%} > {max_dev:.0%}")
                score -= 30
            else:
                issues.append(f"价格锚点 OK（偏差 {dev:.1%}）")

        sources = snap.get("sources") or {}
        required = context.settings.get("data_audit", {}).get(
            "required_source_categories", ["quote", "flow", "sentiment"]
        )
        missing = [c for c in required if c not in sources]
        if missing:
            issues.append(f"来源缺失：{', '.join(missing)}")
            score -= len(missing) * 8

        success = score >= 50 and not any("偏差" in i and ">" in i for i in issues)
        summary = "；".join(issues) if issues else f"标的 {name}({code}) 校验通过"

        return PluginResult(
            name=self.name,
            score=round(max(0.0, min(100.0, score)), 1),
            summary=summary,
            success=success,
            details={"issues": issues, "blocked": not success},
        )


def _f(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

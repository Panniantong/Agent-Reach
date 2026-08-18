# -*- coding: utf-8
"""Weekly variance analysis → harness (dsh-finance variance-analysis)."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_finance import analyze_weekly_variance_bridge
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def _variance_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("finance_variance") or {})


def finance_variance_to_harness_evidence(
    report: dict[str, Any],
    variance: dict[str, Any],
) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    ws = report.get("week_start") or ""
    we = report.get("week_end") or ""
    memory.append(f"weekly variance {ws}~{we}")

    total = variance.get("total_variance")
    if total is not None:
        pct = report.get("weekly_pnl_pct")
        pct_s = f"（{float(pct):+.2f}%）" if pct is not None else ""
        memory.append(f"周盈亏 bridge {float(total):+,.0f}{pct_s}")

    stock = report.get("stock_pnl")
    cash = report.get("cash_pnl")
    if stock is not None or cash is not None:
        parts = []
        if stock is not None:
            parts.append(f"股票 {float(stock):+,.0f}")
        if cash is not None:
            parts.append(f"现金 {float(cash):+,.0f}")
        memory.append("驱动：" + " · ".join(parts))

    if variance.get("reconciled"):
        memory.append(f"bridge 闭合（残差 {float(variance.get('residual') or 0):+,.2f}）")
    else:
        for flag in variance.get("flags") or []:
            memory.append(f"variance：{flag}")
            playbook.append("周六复核 stock/cash 分解与 daily_totals")
            plan.append("finance_variance：修复 bridge 残差后再调阈值")

    if variance.get("material"):
        policy.append("周盈亏 material：下周偏防御，减少激进新开仓")
        playbook.append("material 周盈亏：优先处理浮亏最大持仓")

    holdings = report.get("holdings") or []
    top = sorted(
        [h for h in holdings if h.get("week_chg") is not None],
        key=lambda x: abs(float(x["week_chg"])),
        reverse=True,
    )[:3]
    if top:
        bits = [f"{h.get('name') or h.get('code')} {float(h['week_chg']):+,.0f}" for h in top]
        memory.append("周内贡献：" + "、".join(bits))

    summary = "finance_variance"
    summary += " material" if variance.get("material") else ""
    summary += " ok" if variance.get("reconciled") else " gap"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
        "verification_signals": ["variance_bridge_pass"] if variance.get("reconciled") else ["variance_bridge_gap"],
    }


def apply_finance_variance_harness_refinement(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _variance_cfg(settings)
    if cfg.get("enabled") is False:
        return {"skipped": True, "reason": "finance_variance disabled", "job": "finance_variance"}

    variance = analyze_weekly_variance_bridge(report, settings=settings)
    evidence = finance_variance_to_harness_evidence(report, variance.to_dict())
    domain = {"report": report, "variance": variance.to_dict()}
    evidence["forge_domain"] = domain
    evidence["rigor_domain"] = domain
    refine = apply_skill_refinement(
        "finance_variance",
        evidence,
        settings=settings,
        enabled_flag="finance_variance",
    )
    return {**refine, "job": "finance_variance", "variance": variance.to_dict()}

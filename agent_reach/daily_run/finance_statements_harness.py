# -*- coding: utf-8
"""Weekly financial statements → harness (dsh-finance financial-statements)."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_finance import build_weekly_financial_statements
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def _statements_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("finance_statements") or {})


def finance_statements_to_harness_evidence(
    report: dict[str, Any],
    statements: dict[str, Any],
) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    ws = report.get("week_start") or ""
    we = report.get("week_end") or ""
    memory.append(f"weekly statements {ws}~{we}")

    income = statements.get("income_statement") or {}
    balance = statements.get("balance_sheet") or {}
    cashflow = statements.get("cash_flow") or {}

    net = income.get("net_income")
    if net is not None:
        pct = report.get("weekly_pnl_pct")
        pct_s = f"（{float(pct):+.2f}%）" if pct is not None else ""
        memory.append(f"损益表 净利润 {float(net):+,.0f}{pct_s}")
    if balance.get("assets_total") is not None:
        memory.append(
            f"资产负债表 资产 {float(balance['assets_total']):,.0f} "
            f"现金 {float(balance.get('cash') or 0):,.0f} "
            f"持仓 {float(balance.get('investments') or 0):,.0f}"
        )
    if cashflow.get("operating") is not None:
        memory.append(f"现金流 经营 {float(cashflow['operating']):+,.0f}")

    if statements.get("material"):
        policy.append("周度 material 盈亏：下周 verify 偏保守")
        playbook.append("material 周损益：优先复盘最大持仓贡献")

    for flag in statements.get("flags") or []:
        memory.append(f"statements：{flag}")
        plan.append("finance_statements：修复三表 tie-out")

    summary = "finance_statements"
    summary += " material" if statements.get("material") else ""
    summary += " ok" if statements.get("reconciled") else " gap"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
        "verification_signals": ["statements_tieout_pass"] if statements.get("reconciled") else ["statements_tieout_gap"],
    }


def apply_finance_statements_harness_refinement(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _statements_cfg(settings)
    if cfg.get("enabled") is False:
        return {"skipped": True, "reason": "finance_statements disabled", "job": "finance_statements"}

    statements = build_weekly_financial_statements(report, settings=settings)
    evidence = finance_statements_to_harness_evidence(report, statements)
    domain = {"report": report, "statements": statements}
    evidence["forge_domain"] = domain
    evidence["rigor_domain"] = domain
    refine = apply_skill_refinement(
        "finance_statements",
        evidence,
        settings=settings,
        enabled_flag="finance_statements",
    )
    return {**refine, "job": "finance_statements", "statements": statements}

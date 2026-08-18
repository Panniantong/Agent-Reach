# -*- coding: utf-8
"""Trade ledger journal-entry validation → harness (dsh-finance journal-entry)."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_finance import run_finance_ledger_checks
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def _ledger_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("finance_ledger") or {})


def finance_ledger_to_harness_evidence(
    checks: dict[str, Any],
    *,
    portfolio_summary: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    journal = checks.get("journal") or {}
    period = journal.get("period") or (portfolio_summary or {}).get("as_of")
    memory.append(
        f"ledger journal {period} · {journal.get('entries_checked', 0)} 条 / "
        f"{journal.get('actions_checked', 0)} 分录"
    )

    if journal.get("balanced"):
        memory.append(
            f"借贷平衡 debit={float(journal.get('total_debit') or 0):,.2f} "
            f"credit={float(journal.get('total_credit') or 0):,.2f}"
        )
    else:
        memory.append(f"借贷差 {float(journal.get('difference') or 0):+,.2f} 元")

    for flag in journal.get("blocking_flags") or []:
        memory.append(f"blocking：{flag}")
        playbook.append("ledger 分录校验失败：核对 amount/shares/price 与 FIFO 成本")
        plan.append(f"finance_ledger：修复 {flag}")

    for flag in journal.get("review_flags") or []:
        memory.append(f"review：{flag}")
        if "cost_basis" in flag or "backfill" in flag:
            plan.append("finance_ledger：运行 daily-run pnl backfill")
            playbook.append("卖出缺 cost_basis 时先 backfill 再 refine")
        if "trade_cash_flow" in flag:
            playbook.append("核对 portfolio trade_cash_flow 与 ledger 重算")

    if journal.get("ready_for_review"):
        memory.append("journal ready_for_review（未授权过账）")
    elif not journal.get("balanced"):
        policy.append("ledger 未平衡：下日禁止依赖 ledger 已实现盈亏做 aggressive 决策")

    pf = portfolio_summary or {}
    if pf.get("realized_pnl") is not None and journal.get("balanced"):
        memory.append(f"当日已实现 {float(pf['realized_pnl']):+,.0f}（ledger 校验通过）")

    summary = "finance_ledger"
    summary += " pass" if checks.get("passed") else " block"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
        "verification_signals": ["ledger_journal_pass"] if checks.get("passed") else ["ledger_journal_block"],
        "structured_review_complete": bool(journal.get("ready_for_review")),
        "audit_passed": bool(journal.get("balanced")),
    }


def apply_finance_ledger_harness_refinement(
    portfolio_summary: Optional[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not portfolio_summary:
        return {"skipped": True, "reason": "no portfolio_summary", "job": "finance_ledger"}

    cfg = _ledger_cfg(settings)
    if cfg.get("enabled") is False:
        return {"skipped": True, "reason": "finance_ledger disabled", "job": "finance_ledger"}

    checks = run_finance_ledger_checks(portfolio_summary, settings=settings)
    evidence = finance_ledger_to_harness_evidence(checks, portfolio_summary=portfolio_summary)
    evidence["forge_domain"] = {
        "portfolio_summary": portfolio_summary,
        "journal": checks.get("journal"),
        "trades": portfolio_summary.get("trades") or [],
    }
    evidence["rigor_domain"] = dict(evidence["forge_domain"])
    refine = apply_skill_refinement(
        "finance_ledger",
        evidence,
        settings=settings,
        enabled_flag="finance_ledger",
    )
    return {**refine, "job": "finance_ledger", "checks": checks}

# -*- coding: utf-8
"""Trade ledger journal-entry prep → harness (dsh-finance journal-entry-prep)."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_finance import run_finance_ledger_prep_checks
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def _prep_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("finance_ledger_prep") or {})


def finance_ledger_prep_to_harness_evidence(
    checks: dict[str, Any],
    *,
    portfolio_summary: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    prep = checks.get("prep") or {}
    period = prep.get("period") or (portfolio_summary or {}).get("as_of")
    memory.append(
        f"ledger prep {period} · {prep.get('entries_checked', 0)} 条 / "
        f"{prep.get('actions_checked', 0)} 分录待审"
    )

    material_rules = [
        r for r in (prep.get("approval_matrix") or []) if r.get("needs_reasoning") or r.get("needs_approver")
    ]
    if material_rules:
        memory.append(f"approval matrix material 规则 {len(material_rules)} 条")

    for flag in prep.get("blocking_flags") or []:
        memory.append(f"prep blocking：{flag}")
        plan.append(f"finance_ledger_prep：修复 {flag}")

    for flag in prep.get("review_flags") or []:
        memory.append(f"prep review：{flag}")
        playbook.append("ledger prep：补齐 reasoning / approved_by / cost_basis 后再 journal check")
        plan.append("finance_ledger_prep：补文档后再 finance_ledger")

    if prep.get("ready_for_journal"):
        memory.append("ledger prep ready_for_journal")
    else:
        policy.append("ledger prep 未完成：禁止进入 finance_ledger 过账校验")

    summary = "finance_ledger_prep"
    summary += " ready" if checks.get("passed") else " block"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
        "verification_signals": ["ledger_prep_ready"] if checks.get("passed") else ["ledger_prep_block"],
        "structured_review_complete": bool(prep.get("ready_for_journal")),
        "audit_passed": bool(prep.get("ready_for_journal")),
    }


def apply_finance_ledger_prep_harness_refinement(
    portfolio_summary: Optional[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not portfolio_summary:
        return {"skipped": True, "reason": "no portfolio_summary", "job": "finance_ledger_prep"}

    cfg = _prep_cfg(settings)
    if cfg.get("enabled") is False:
        return {"skipped": True, "reason": "finance_ledger_prep disabled", "job": "finance_ledger_prep"}

    checks = run_finance_ledger_prep_checks(portfolio_summary, settings=settings)
    evidence = finance_ledger_prep_to_harness_evidence(checks, portfolio_summary=portfolio_summary)
    evidence["forge_domain"] = {
        "portfolio_summary": portfolio_summary,
        "prep": checks.get("prep"),
        "trades": portfolio_summary.get("trades") or [],
    }
    evidence["rigor_domain"] = dict(evidence["forge_domain"])
    refine = apply_skill_refinement(
        "finance_ledger_prep",
        evidence,
        settings=settings,
        enabled_flag="finance_ledger_prep",
    )
    return {**refine, "job": "finance_ledger_prep", "checks": checks}

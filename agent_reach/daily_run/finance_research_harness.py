# -*- coding: utf-8
"""Structured finance research workflow → harness (dsh-finance finance_research_workflow)."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_finance import build_finance_research_workflow
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def _research_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("finance_research") or {})


def finance_research_to_harness_evidence(
    report: dict[str, Any],
    workflow: dict[str, Any],
) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    period = workflow.get("period") or ""
    memory.append(f"finance_research {period or 'weekly'}")
    memory.append(f"来源 {len(workflow.get('sources') or [])} · 查询 {len(workflow.get('queries') or [])}")

    for src in (workflow.get("sources") or [])[:4]:
        memory.append(f"source[{src.get('kind')}]: {src.get('title')}")

    for row in (workflow.get("queries") or [])[:4]:
        plan.append(f"research：{row.get('query')}")
        if row.get("priority") == "high":
            playbook.append(f"优先调研 {row.get('topic')}")

    for gap in workflow.get("evidence_gaps") or []:
        memory.append(f"gap：{gap}")
        playbook.append(f"research gap：{gap}")

    if workflow.get("ready_for_review"):
        memory.append("research workflow ready_for_review")
    else:
        policy.append("research 证据不足：下日勿仅凭未验证摘录调仓")

    summary = "finance_research"
    summary += " ready" if workflow.get("ready_for_review") else " gap"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
        "verification_signals": ["research_ready"] if workflow.get("ready_for_review") else ["research_gap"],
        "structured_review_complete": bool(workflow.get("ready_for_review")),
    }


def apply_finance_research_harness_refinement(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    forecast: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _research_cfg(settings)
    if cfg.get("enabled") is False:
        return {"skipped": True, "reason": "finance_research disabled", "job": "finance_research"}

    workflow = build_finance_research_workflow(report, settings=settings, forecast=forecast)
    evidence = finance_research_to_harness_evidence(report, workflow)
    domain = {"report": report, "workflow": workflow, "forecast": forecast or {}}
    evidence["forge_domain"] = domain
    evidence["rigor_domain"] = domain
    refine = apply_skill_refinement(
        "finance_research",
        evidence,
        settings=settings,
        enabled_flag="finance_research",
    )
    return {**refine, "job": "finance_research", "workflow": workflow}

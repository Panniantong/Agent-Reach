# -*- coding: utf-8
"""Next-week close management calendar → harness (dsh-finance close-management)."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_finance import build_close_management_plan
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def _plan_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("finance_close_plan") or {})


def finance_close_plan_to_harness_evidence(plan: dict[str, Any]) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan_lines: list[str] = []

    ws = plan.get("week_start") or ""
    we = plan.get("week_end") or ""
    memory.append(f"close_plan 窗口 {ws}~{we} · {len(plan.get('tasks') or [])} 项")

    for task in plan.get("tasks") or []:
        day = task.get("day") or "T+?"
        title = task.get("title") or ""
        status = task.get("status") or "pending"
        line = f"{day} {title}"
        if status == "blocked":
            plan_lines.append(f"close_plan blocked：{title}")
            policy.append(f"下周门禁：{title}")
        else:
            playbook.append(line)
        memory.append(line)

    for blocker in plan.get("blockers") or []:
        memory.append(f"blocker：{blocker}")
        plan_lines.append(f"close_plan：先解除 {blocker}")

    critical = plan.get("critical_path") or []
    if critical:
        memory.append("关键路径：" + " → ".join(str(x) for x in critical[:4]))

    summary = f"finance_close_plan tasks={len(plan.get('tasks') or [])}"
    if plan.get("blockers"):
        summary += f" blockers={len(plan['blockers'])}"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan_lines,
        "summary": summary,
        "verification_signals": ["close_plan_blocked"] if plan.get("blockers") else ["close_plan_ready"],
    }


def apply_finance_close_plan_harness_refinement(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    skill_writeback: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _plan_cfg(settings)
    if cfg.get("enabled") is False:
        return {"skipped": True, "reason": "finance_close_plan disabled", "job": "finance_close_plan"}

    plan = build_close_management_plan(
        report,
        settings=settings,
        skill_writeback=skill_writeback,
    )
    evidence = finance_close_plan_to_harness_evidence(plan)
    domain = {"report": report, "plan": plan}
    evidence["forge_domain"] = domain
    evidence["rigor_domain"] = domain
    refine = apply_skill_refinement(
        "finance_close_plan",
        evidence,
        settings=settings,
        enabled_flag="finance_close_plan",
    )
    return {**refine, "job": "finance_close_plan", "close_plan": plan}

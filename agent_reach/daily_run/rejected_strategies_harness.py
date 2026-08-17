# -*- coding: utf-8
"""Rejected / falsified strategies → harness memory + plan."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def _rejected_harness_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    cfg = settings or {}
    harness = cfg.get("harness") or {}
    if harness.get("enabled") is False:
        return False
    rejected_cfg = cfg.get("rejected_strategies") or {}
    if rejected_cfg.get("harness_evolve", True) is False:
        return False
    return True


def rejected_to_harness_evidence(
    *,
    title: str,
    reason: str = "",
    blocked: Optional[list[str]] = None,
    source: str = "weekly",
) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    if title:
        memory.append(f"已证伪策略：{title} — {reason}".strip(" —"))
        plan.append(f"rejected：勿重复写回「{title[:48]}」")
        if any(p in f"{title} {reason}" for p in ("接飞刀", "激进建仓", "加大仓位")):
            policy.append("宏观一票否决生效：维持高现金，禁止接飞刀")

    for name in blocked or []:
        if name and name != title:
            memory.append(f"已证伪策略跳过：{name}")
            plan.append(f"rejected blocked：{name[:48]}")

    summary = f"rejected {title or 'batch'} blocked={len(blocked or [])}"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def apply_rejected_strategies_harness_refinement(
    *,
    title: str = "",
    reason: str = "",
    blocked: Optional[list[str]] = None,
    source: str = "weekly",
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not _rejected_harness_enabled(settings):
        return {"skipped": True, "reason": "rejected harness disabled", "job": "rejected_strategies"}
    evidence = rejected_to_harness_evidence(
        title=title,
        reason=reason,
        blocked=blocked,
        source=source,
    )
    if not any(evidence.get(k) for k in ("memory", "policy", "playbook", "plan")):
        return {"skipped": True, "reason": "empty evidence", "job": "rejected_strategies"}
    return apply_skill_refinement("rejected_strategies", evidence, settings=settings)

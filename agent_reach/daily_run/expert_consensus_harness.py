# -*- coding: utf-8
"""8-expert / MSS expert outputs → harness policy closed loop."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_experts import run_expert_consensus_checks
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def _consensus_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("expert_consensus") or {})


def expert_consensus_to_harness_evidence(
    checks: dict[str, Any],
    *,
    snapshot: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    review = checks.get("review") or {}
    if not review:
        return {}

    wf = review.get("workflow") or "close"
    memory.append(
        f"expert_consensus {wf} · {review.get('expert_count', 0)} 专家 · "
        f"{review.get('consensus_score')} 分 · {review.get('consensus_label')}"
    )

    for conflict in review.get("conflicts") or []:
        memory.append(f"专家冲突：{conflict}")
        playbook.append(f"supervisor 仲裁：{conflict}")

    for drift in review.get("mss_drift") or []:
        memory.append(f"MSS drift：{drift}")
        plan.append(f"expert_consensus：校准 {drift}")

    if review.get("low_scorers"):
        memory.append("低分专家：" + "，".join(review["low_scorers"][:4]))
    if review.get("high_scorers"):
        memory.append("高分专家：" + "，".join(review["high_scorers"][:4]))

    if review.get("blocked"):
        reason = review.get("block_reason") or "专家鉴别未通过"
        memory.append(f"identifier block：{reason}")
        policy.append("专家鉴别未通过：禁止激进加仓与追高")
        plan.append("expert_consensus：修复 identifier 失败原因后再调仓")

    label = str(review.get("consensus_label") or "")
    if label == "回避":
        policy.append("Team 共识回避：维持高现金，禁止接飞刀")
    elif label == "观察":
        policy.append("Team 共识观察：仅允许小仓试探，禁止满仓进攻")
    elif label == "可做" and review.get("conflicts"):
        policy.append("Team 可做但存在专家冲突：调仓前需 supervisor 书面仲裁")
        playbook.append("冲突态可做：先减码验证再放大仓位")

    counter = str(review.get("counter_thesis") or "")
    if counter:
        playbook.append(counter)

    for flag in checks.get("blocking_flags") or []:
        memory.append(f"consensus blocking：{flag}")

    summary = f"expert_consensus {wf} {label or '—'}"
    summary += " block" if review.get("blocked") else ""
    summary += " drift" if review.get("mss_drift") else ""

    verification_signals: list[str] = []
    if review.get("blocked"):
        verification_signals.append("expert_identifier_blocked")
    if review.get("conflicts"):
        verification_signals.append("expert_conflicts")
    if review.get("mss_drift"):
        verification_signals.append("expert_mss_drift")

    name = (snapshot or {}).get("name") or (snapshot or {}).get("code") or ""
    if name:
        memory.insert(0, f"标的 {name}")

    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
        "verification_signals": verification_signals,
        "structured_review_complete": bool(review.get("ready_for_policy")),
        "audit_passed": bool(checks.get("passed")),
    }


def apply_expert_consensus_harness_refinement(
    snapshot: Optional[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
    workflow: str = "close",
) -> dict[str, Any]:
    if not snapshot:
        return {"skipped": True, "reason": "no snapshot", "job": "expert_consensus"}

    cfg = _consensus_cfg(settings)
    if cfg.get("enabled") is False:
        return {"skipped": True, "reason": "expert_consensus disabled", "job": "expert_consensus"}

    wf = workflow
    wf_flags = cfg.get("workflows") or {}
    if isinstance(wf_flags, dict) and wf_flags.get(wf) is False:
        return {"skipped": True, "reason": f"workflow {wf} disabled", "job": "expert_consensus"}

    checks = run_expert_consensus_checks(snapshot, settings=settings, workflow=wf)
    if checks.get("skipped"):
        return {"skipped": True, "reason": checks.get("reason"), "job": "expert_consensus"}

    evidence = expert_consensus_to_harness_evidence(checks, snapshot=snapshot)
    if not any(evidence.get(k) for k in ("memory", "policy", "playbook", "plan")):
        return {"skipped": True, "reason": "empty evidence", "job": "expert_consensus"}

    domain = {
        "snapshot": snapshot,
        "review": checks.get("review"),
        "checks": checks,
        "expert_results": snapshot.get("expert_results") or [],
        "expert_scores": snapshot.get("expert_scores") or {},
        "mss_breakdown": snapshot.get("mss_breakdown") or {},
        "workflow": wf,
    }
    evidence["forge_domain"] = domain
    evidence["rigor_domain"] = domain
    refine = apply_skill_refinement(
        "expert_consensus",
        evidence,
        settings=settings,
        enabled_flag="expert_consensus",
    )
    return {**refine, "job": "expert_consensus", "checks": checks}

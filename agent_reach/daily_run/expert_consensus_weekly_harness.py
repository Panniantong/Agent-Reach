# -*- coding: utf-8
"""Weekly rollup of session expert_consensus audit → harness policy."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_experts import aggregate_expert_consensus_audit
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement
from agent_reach.daily_run.harness_weekly_narrative import load_apply_audit_in_window, weekly_narrative_cfg


def _weekly_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    base = dict((settings or {}).get("expert_consensus") or {})
    raw = dict(base.get("weekly") or {})
    return {
        "enabled": raw.get("enabled", base.get("weekly_rollup", True)) is not False,
        "audit_days": max(1, int(raw.get("audit_days") or 7)),
        "high_conflict_runs": max(1, int(raw.get("high_conflict_runs") or 3)),
        "high_drift_runs": max(1, int(raw.get("high_drift_runs") or 4)),
    }


def expert_consensus_weekly_to_harness_evidence(
    aggregate: dict[str, Any],
    *,
    report: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    if not aggregate.get("ready_for_review"):
        return {}

    runs = int(aggregate.get("runs") or 0)
    memory.append(
        f"expert_consensus weekly · {runs} 次 session · applied {aggregate.get('applied', 0)}"
    )
    if aggregate.get("mss_only"):
        memory.append(f"MSS-only 路径 {aggregate['mss_only']} 次")
    if aggregate.get("full_team"):
        memory.append(f"Team-First 路径 {aggregate['full_team']} 次")

    workflows = aggregate.get("workflows") or {}
    if workflows:
        wf_bits = [f"{name}×{count}" for name, count in workflows.items()]
        memory.append("workflow 分布：" + "，".join(wf_bits))

    conflicts = int(aggregate.get("conflicts") or 0)
    drift = int(aggregate.get("drift") or 0)
    blocked = int(aggregate.get("blocked") or 0)
    if conflicts:
        memory.append(f"本周专家冲突 session {conflicts} 次")
    if drift:
        memory.append(f"本周 MSS drift session {drift} 次")
    if blocked:
        memory.append(f"本周 identifier block {blocked} 次")
        policy.append("本周 identifier 曾阻断：下周调仓前复核鉴别 Agent 摘要")

    if conflicts >= 3:
        playbook.append("高频专家冲突：收盘前强制 supervisor 仲裁 tech vs risk")
    if drift >= 4:
        plan.append("expert_consensus_weekly：校准 mss_drift_threshold 或 breakdown 数据源")

    week = ""
    if report:
        week = f"{report.get('week_start', '')}~{report.get('week_end', '')}"
        if week != "~":
            memory.insert(0, f"周度 {week}")

    summary = f"expert_consensus_weekly runs={runs} conflicts={conflicts}"
    signals = ["expert_weekly_ready"]
    if conflicts:
        signals.append("expert_weekly_conflicts")
    if drift:
        signals.append("expert_weekly_drift")

    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
        "verification_signals": signals,
        "structured_review_complete": True,
    }


def apply_expert_consensus_weekly_harness_refinement(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _weekly_cfg(settings)
    if cfg.get("enabled") is False:
        return {"skipped": True, "reason": "expert_consensus weekly disabled", "job": "expert_consensus_weekly"}

    narrative_cfg = weekly_narrative_cfg(settings)
    audit_rows = load_apply_audit_in_window(
        week_start=report.get("week_start"),
        week_end=report.get("week_end"),
        days=cfg["audit_days"] or narrative_cfg["audit_days"],
    )
    aggregate = aggregate_expert_consensus_audit(audit_rows)
    if not aggregate.get("ready_for_review"):
        return {"skipped": True, "reason": "no expert_consensus audit rows", "job": "expert_consensus_weekly"}

    evidence = expert_consensus_weekly_to_harness_evidence(aggregate, report=report)
    if not any(evidence.get(k) for k in ("memory", "policy", "playbook", "plan")):
        return {"skipped": True, "reason": "empty evidence", "job": "expert_consensus_weekly"}

    domain = {"report": report, "aggregate": aggregate, "audit_rows": len(audit_rows)}
    evidence["forge_domain"] = domain
    evidence["rigor_domain"] = domain
    refine = apply_skill_refinement(
        "expert_consensus_weekly",
        evidence,
        settings=settings,
        enabled_flag="expert_consensus",
    )
    return {**refine, "job": "expert_consensus_weekly", "aggregate": aggregate}

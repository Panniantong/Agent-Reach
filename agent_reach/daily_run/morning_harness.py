# -*- coding: utf-8
"""Morning pipeline findings → harness self-evolution."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def morning_to_harness_evidence(run_result: dict[str, Any]) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    snapshot = run_result.get("snapshot") or {}
    evaluation = run_result.get("evaluation") or {}
    report = evaluation.get("report") or {}
    gate = evaluation.get("gate")
    audit = evaluation.get("audit")

    name = report.get("name") or snapshot.get("name") or report.get("code") or "标的"
    mss = report.get("mss_final")
    verdict = report.get("verdict")
    if mss is not None:
        memory.append(f"早盘 {name} MSS={mss} verdict={verdict}")

    if verdict == "回避":
        memory.append("宏观一票否决生效：维持高现金，禁止接飞刀")
        policy.append("宏观一票否决生效：维持高现金，禁止接飞刀")
    elif verdict == "观察":
        cash = (snapshot.get("portfolio") or {}).get("cash_ratio")
        if cash is not None and float(cash) >= 0.4:
            memory.append(f"观察态下现金 {float(cash):.0%} 符合风控")

    if gate is not None and not gate.passed:
        memory.append(f"早盘门禁未通过：{gate.summary()}")
        plan.append(f"morning gate：{name} 修复数据质量后再激进操作")

    if audit is not None and not audit.passed:
        memory.append(f"早盘审计未通过：{audit.summary()}")
        plan.append("morning audit：补全 quote/flow/sentiment 来源")

    plan_close = run_result.get("harness_plan_closeout") or {}
    if plan_close.get("count"):
        memory.append(f"周一 harness plan 关闭 {plan_close['count']} 条")

    for rec in (report.get("recommendations") or [])[:2]:
        playbook.append(f"早盘建议：{rec}")

    summary = f"morning {name} mss={mss} verdict={verdict}"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def apply_morning_harness_refinement(
    run_result: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    evidence = morning_to_harness_evidence(run_result)
    if not any(evidence.get(k) for k in ("memory", "policy", "playbook", "plan")):
        return {"skipped": True, "reason": "empty evidence", "job": "morning"}
    return apply_skill_refinement("morning", evidence, settings=settings)

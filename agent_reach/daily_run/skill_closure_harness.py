# -*- coding: utf-8
"""Weekly skill closure improvements → harness (skip JSON when harness mode)."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def weekly_report_to_harness_evidence(report: dict[str, Any]) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    ws = report.get("week_start") or ""
    we = report.get("week_end") or ""
    if ws and we:
        memory.append(f"skill_closure 窗口 {ws}~{we}")

    for item in report.get("process_improvements") or []:
        title = str(item.get("title") or "改进")
        detail = str(item.get("detail") or "")
        action = str(item.get("action") or "")
        category = str(item.get("category") or "")
        priority = str(item.get("priority") or "")
        line = f"{category}/{priority}：{title} — {detail}"
        playbook.append(line + (f"；执行：{action}" if action else ""))

        blob = f"{title} {detail} {action}"
        if category == "mss" or "预测未命中" in blob:
            memory.append("MSS 预测偏离：下日调低进攻阈值或缩窄仓位")
            playbook.append("增大 mss_forecast.base_spread 或运行 daily-run optimize")
        if category == "schedule" and priority == "high":
            memory.append("缺失收盘复盘：经验沉淀中断，下日补跑 close")
            plan.append(f"schedule high：{title}")
        if category == "portfolio":
            plan.append(f"portfolio：{title}")
        if priority in ("high", "medium"):
            plan.append(f"下周：{title}" + (f" → {action}" if action else ""))

    for item in report.get("skill_learning") or []:
        title = item.get("title") or "技能"
        summary = item.get("summary") or ""
        memory.append(f"{title}：{summary}")

    blocked = report.get("_rejected_blocked") or []
    for title in blocked[:5]:
        memory.append(f"已证伪策略跳过：{title}")

    gates = report.get("skill_gate_failures") or []
    for gate in gates[:5]:
        plan.append(f"skill_gate：{gate}")

    summary = f"skill_closure improvements={len(report.get('process_improvements') or [])}"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def apply_skill_closure_harness_refinement(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    evidence = weekly_report_to_harness_evidence(report)
    return apply_skill_refinement(
        "skill_closure",
        evidence,
        settings=settings,
        enabled_flag="weekly_report",
    )


def harness_mode_blocks_settings_writeback(settings: dict[str, Any]) -> bool:
    from agent_reach.daily_run.harness_policy import harness_evolution_mode

    return harness_evolution_mode(settings) == "harness"

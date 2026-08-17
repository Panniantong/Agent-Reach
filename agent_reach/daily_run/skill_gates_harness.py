# -*- coding: utf-8
"""Skill gate failures → harness plan (Saturday writeback guardrails)."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def _skill_gates_harness_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    cfg = settings or {}
    gates_cfg = (cfg.get("weekly_report") or {}).get("skill_gates") or {}
    if gates_cfg.get("harness_evolve", True) is False:
        return False
    harness = cfg.get("harness") or {}
    return harness.get("enabled") is not False


def skill_gates_to_harness_evidence(gate_result: dict[str, Any]) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    for failure in gate_result.get("failures") or []:
        text = str(failure)
        memory.append(f"skill_gate 失败：{text}")
        plan.append(f"skill_gate 修复：{text[:120]}")
        if "playbook" in text:
            playbook.append("周六写回后检查 playbook 片段 fingerprint 与 manifest 一致")
        if "experience" in text:
            playbook.append("周六写回后检查 experience 片段与 weekly report 对齐")
        if "行数" in text:
            policy.append("skill 文件超行数：启用 compact_experience_sections 归档")

    for warn in gate_result.get("warnings") or []:
        playbook.append(f"skill_gate warn：{warn}")

    if gate_result.get("block_weekly_push"):
        memory.append("Skill 门禁阻断周报推送：须修复后再 push")

    summary = f"skill_gates ok={gate_result.get('ok')} failures={len(gate_result.get('failures') or [])}"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def apply_skill_gates_harness_refinement(
    gate_result: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if gate_result.get("skipped") or gate_result.get("ok") is not False:
        return {"skipped": True, "reason": "gates passed or skipped", "job": "skill_gates"}
    if not _skill_gates_harness_enabled(settings):
        return {"skipped": True, "reason": "skill_gates harness disabled", "job": "skill_gates"}
    evidence = skill_gates_to_harness_evidence(gate_result)
    return apply_skill_refinement("skill_gates", evidence, settings=settings)

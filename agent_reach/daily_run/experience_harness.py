# -*- coding: utf-8
"""Close experience rules → harness (consolidates runtime evolution with experience.jsonl)."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.experience import _distill_rules
from agent_reach.daily_run.harness_policy import harness_evolution_mode
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def experience_harness_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    cfg = settings or {}
    exp = cfg.get("experience") or {}
    if exp.get("harness_evolve", True) is False:
        return False
    harness = cfg.get("harness")
    if not isinstance(harness, dict):
        return False
    if harness.get("enabled") is False:
        return False
    return harness_evolution_mode(cfg) == "harness"


def experience_consolidated_mode(settings: Optional[dict[str, Any]] = None) -> bool:
    """When True, rules live in harness only — jsonl/rules_summary stay metadata-only."""
    cfg = settings or {}
    exp = cfg.get("experience") or {}
    if exp.get("harness_consolidate", True) is False:
        return False
    return experience_harness_enabled(cfg)


def experience_to_harness_evidence(
    snapshot: dict[str, Any],
    verify: dict[str, Any],
    *,
    rules: Optional[list[str]] = None,
    curve: Optional[dict[str, Any]] = None,
    forecast_review: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    name = snapshot.get("name") or verify.get("code") or "标的"
    distilled = rules if rules is not None else _distill_rules(
        snapshot, verify, curve, forecast_review=forecast_review
    )
    for rule in distilled:
        memory.append(rule)
        if "宏观一票否决" in rule or "禁止接飞刀" in rule:
            policy.append("宏观一票否决生效：维持高现金，禁止接飞刀")
        if "MSS 预测偏离" in rule:
            playbook.append("增大 mss_forecast.base_spread 或运行 daily-run optimize")
            plan.append(f"experience：{name} MSS 预测偏离跟进")
        if "尾盘曲线" in rule and "防御" in rule:
            plan.append(f"experience：{name} 次日早盘偏防御")

    mss = snapshot.get("mss_final") or verify.get("mss_current")
    verdict = verify.get("verdict_current")
    if mss is not None:
        memory.append(f"experience {name} MSS={mss} verdict={verdict}")
    if verify.get("prediction_hit") is False or verify.get("mss_within_prediction") is False:
        memory.append("MSS 预测偏离：下日调低进攻阈值或缩窄仓位")

    summary = f"experience {name} rules={len(distilled)}"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def apply_experience_harness_refinement(
    snapshot: dict[str, Any],
    verify: dict[str, Any],
    *,
    rules: Optional[list[str]] = None,
    curve: Optional[dict[str, Any]] = None,
    forecast_review: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not experience_harness_enabled(settings):
        return {"skipped": True, "reason": "experience harness disabled", "job": "experience"}
    evidence = experience_to_harness_evidence(
        snapshot,
        verify,
        rules=rules,
        curve=curve,
        forecast_review=forecast_review,
    )
    return apply_skill_refinement("experience", evidence, settings=settings)

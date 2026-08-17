# -*- coding: utf-8
"""Close improvements → harness self-evolution."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.close_improvements import CloseImprovements, ImprovementItem
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def _item_to_harness(item: ImprovementItem) -> tuple[list[str], list[str], list[str], list[str]]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []
    blob = f"{item.title} {item.detail}"
    line = f"{item.category}/{item.priority}：{item.title} — {item.detail}"

    if item.category == "mss":
        memory.append(line)
        if "预测" in blob or "MSS" in blob:
            memory.append("MSS 预测偏离：下日调低进攻阈值或缩窄仓位")
            playbook.append("增大 mss_forecast.base_spread 或运行 daily-run optimize")
        if "技术" in blob or "MA20" in blob:
            memory.append("技术面因子拖累 MSS：确认 AKShare 历史 K 线可用")

    elif item.category == "portfolio":
        memory.append(line)
        if "现金" in blob:
            memory.append("维持高现金：禁止接飞刀，取消一切买入")
        if "macro_veto" in blob or "卖出" in blob or "弱势" in blob:
            plan.append(f"portfolio：{item.title}")
        if "锁定期" in blob or "holding_lock" in blob:
            playbook.append(f"holding_lock_days 生效：{item.detail[:120]}")

    elif item.category == "watchlist":
        playbook.append(line)
        if "重复" in blob or "上限" in blob:
            plan.append(f"watchlist：{item.title}")

    elif item.category == "schedule":
        playbook.append(line)
        if "扫描" in blob and ("缺失" in blob or "偏少" in blob or "空档" in blob):
            memory.append("盘中扫描偏少：intraday 次数不足，下日 trade_min_scans 可降至 2")
        if "调仓" in blob and "频" in blob:
            memory.append("减少频繁调仓：摩擦成本过高时提高 friction_min_return_pct")
        if item.priority == "high":
            plan.append(f"schedule：{item.title}")

    if item.priority == "high" and not plan:
        plan.append(f"close_improve high：{item.title}")

    return memory, policy, playbook, plan


def improvements_to_harness_evidence(improvements: CloseImprovements) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []
    seen: set[str] = set()

    def _extend(kind: str, lines: list[str]) -> None:
        for line in lines:
            if not line or line in seen:
                continue
            seen.add(line)
            {"memory": memory, "policy": policy, "playbook": playbook, "plan": plan}[kind].append(line)

    for item in improvements.items:
        m, p, pb, pl = _item_to_harness(item)
        _extend("memory", m)
        _extend("policy", p)
        _extend("playbook", pb)
        _extend("plan", pl)

    high = sum(1 for i in improvements.items if i.priority == "high")
    summary = f"close_improve items={len(improvements.items)} high={high}"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def forecast_review_to_harness_evidence(forecast_review: dict[str, Any]) -> dict[str, Any]:
    memory: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    acc = forecast_review.get("accuracy")
    total = int(forecast_review.get("symbol_total") or 0)
    if acc is not None and total > 0:
        memory.append(f"周预测命中率 {float(acc):.0%}（{forecast_review.get('symbol_hits', 0)}/{total}）")
    if forecast_review.get("mss_hit") is False:
        memory.append("MSS 预测偏离：下日调低进攻阈值或缩窄仓位")
        playbook.append("增大 mss_forecast.base_spread 或检查 macro 因子滞后")
    for note in forecast_review.get("optimization_notes") or []:
        playbook.append(str(note)[:200])

    if forecast_review.get("mss_hit") is False:
        plan.append("forecast_review：校准 base_spread / vol_multiplier")

    return {
        "memory": memory,
        "policy": [],
        "playbook": playbook,
        "plan": plan,
        "summary": f"forecast_review acc={acc}",
    }


def apply_close_improve_harness_refinement(
    improvements: CloseImprovements,
    *,
    settings: Optional[dict[str, Any]] = None,
    forecast_review: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from agent_reach.daily_run.harness_skill_base import merge_harness_evidence

    parts = [improvements_to_harness_evidence(improvements)]
    if forecast_review:
        parts.append(forecast_review_to_harness_evidence(forecast_review))
    evidence = merge_harness_evidence(*parts)
    return apply_skill_refinement("close_improve", evidence, settings=settings, enabled_flag="close_improvements")

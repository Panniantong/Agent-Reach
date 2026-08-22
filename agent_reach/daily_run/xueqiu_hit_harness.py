# -*- coding: utf-8
"""Xueqiu hot-hit settlement → harness memory/playbook."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement
from agent_reach.daily_run.xueqiu_hit_outcomes import summarize_xueqiu_hit_outcomes, xueqiu_hit_outcomes_enabled


def xueqiu_hit_harness_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    if not xueqiu_hit_outcomes_enabled(settings):
        return False
    cfg = settings or {}
    macro = cfg.get("macro_collector") or {}
    nested = macro.get("xueqiu_hit_outcomes") or {}
    if nested.get("harness_evolve") is False:
        return False
    if macro.get("xueqiu_hit_harness_evolve") is False:
        return False
    harness = cfg.get("harness") or {}
    if harness.get("enabled") is False:
        return False
    return True


def xueqiu_hit_to_harness_evidence(
    settled: list[dict[str, Any]],
    *,
    stats: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    summary_stats = stats or summarize_xueqiu_hit_outcomes()
    hit_rate = summary_stats.get("hit_rate")
    if summary_stats.get("total"):
        memory.append(
            f"xueqiu_hit 近样本 {summary_stats['total']} 条，命中率 {hit_rate:.0%}"
            if isinstance(hit_rate, (int, float))
            else f"xueqiu_hit 近样本 {summary_stats['total']} 条"
        )

    for row in settled:
        outcome = row.get("outcome")
        name = row.get("name") or row.get("code") or "标的"
        hit_type = row.get("hit_type") or "hot_stock"
        reason = str(row.get("reason") or "")
        if outcome == "hit":
            memory.append(f"xueqiu {hit_type} 命中 {name}：{reason}")
            if hit_type == "hot_stock":
                playbook.append("雪球人气榜重叠时可适度提高 sentiment 权重参考")
        elif outcome == "miss":
            memory.append(f"xueqiu {hit_type} 未中 {name}：{reason}")
            policy.append("热榜信号未兑现时下调当日追涨冲动，优先看 MSS 与北向")
            plan.append(f"xueqiu_hit：{name} 热榜落空，次日早盘偏防御")
        elif outcome == "neutral":
            memory.append(f"xueqiu {hit_type} 中性 {name}：{reason}")

    if summary_stats.get("misses", 0) >= 3 and isinstance(hit_rate, (int, float)) and hit_rate < 0.4:
        policy.append("雪球热榜近窗命中率偏低，macro_collector 热榜 boost 宜保守")
        playbook.append("portfolio_hot_stock_boost 偏高时可运行 daily-run optimize 回测")

    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": f"xueqiu_hit settled={len(settled)}",
    }


def apply_xueqiu_hit_harness_refinement(
    settled: list[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not xueqiu_hit_harness_enabled(settings):
        return {"skipped": True, "reason": "xueqiu hit harness disabled", "job": "xueqiu_hit"}
    if not settled:
        return {"skipped": True, "reason": "no settled hits", "job": "xueqiu_hit"}
    evidence = xueqiu_hit_to_harness_evidence(settled)
    return apply_skill_refinement("xueqiu_hit", evidence, settings=settings)

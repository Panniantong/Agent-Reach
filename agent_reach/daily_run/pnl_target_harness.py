# -*- coding: utf-8
"""Next-day P&L target → harness reward/penalty self-evolution."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement
from agent_reach.daily_run.pnl_target import (
    PnlTarget,
    PnlTargetResult,
    _pnl_target_cfg,
    run_pnl_target_close_cycle,
)


def pnl_target_to_harness_evidence(
    cycle: dict[str, Any],
    *,
    portfolio_summary: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _pnl_target_cfg(settings)
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    evaluated = cycle.get("evaluated")
    next_target = cycle.get("next_target")

    if evaluated:
        target_cny = float(evaluated.get("target_pnl_cny") or 0)
        actual_cny = float(evaluated.get("actual_pnl_cny") or 0)
        delta = float(evaluated.get("delta_cny") or 0)
        if evaluated.get("hit"):
            memory.append(
                f"盈亏目标达成：目标 +{target_cny:,.0f} 实际 {actual_cny:+,.0f}（超 {delta:+,.0f}）"
            )
            playbook.append("盈亏目标奖励：维持有效策略，适度进攻")
            policy.append("进攻期：盈亏目标达成，可维持当前仓位纪律")
            if cfg.get("reward_plan"):
                plan.append(str(cfg["reward_plan"]))
        else:
            memory.append(
                f"盈亏目标未达：目标 +{target_cny:,.0f} 实际 {actual_cny:+,.0f}（差 {delta:+,.0f}）"
            )
            policy.append("缩窄仓位：盈亏目标未达，下日偏防御")
            playbook.append("盈亏目标处罚：提高现金纪律，减少新开仓")
            if cfg.get("penalty_plan"):
                plan.append(str(cfg["penalty_plan"]))
            else:
                plan.append("pnl_target：未达目标，优先 verify 回避与 defensive_trim")

    if next_target:
        row = next_target
        pct = row.get("target_pnl_pct")
        pct_s = f"（{float(pct):+.2f}%）" if pct is not None else ""
        memory.append(
            f"下一交易日 {row.get('target_date')} 总盈亏目标 +{float(row['target_pnl_cny']):,.0f}{pct_s}"
        )
        plan.append(
            f"pnl_target：{row.get('target_date')} 达成 +{float(row['target_pnl_cny']):,.0f} 元"
        )

    pf = portfolio_summary or {}
    if pf.get("daily_pnl") is not None and not evaluated:
        memory.append(
            f"当日盈亏 {float(pf['daily_pnl']):+,.0f}（尚无待评目标，已设定下一交易日目标）"
        )

    summary = "pnl_target"
    if evaluated:
        summary += " hit" if evaluated.get("hit") else " miss"
    if next_target:
        summary += f" next={next_target.get('target_date')}"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def apply_pnl_target_harness_refinement(
    portfolio_summary: Optional[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
    cycle: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not portfolio_summary:
        return {"skipped": True, "reason": "no portfolio_summary", "job": "pnl_target"}

    cfg = _pnl_target_cfg(settings)
    if cfg.get("enabled") is False:
        return {"skipped": True, "reason": "pnl_target disabled", "job": "pnl_target"}

    run = cycle or run_pnl_target_close_cycle(portfolio_summary, settings=settings)
    if run.get("skipped"):
        return {**run, "job": "pnl_target"}

    evidence = pnl_target_to_harness_evidence(
        run,
        portfolio_summary=portfolio_summary,
        settings=settings,
    )
    evidence["forge_domain"] = {
        "evaluated": run.get("evaluated"),
        "next_target": run.get("next_target"),
    }
    evidence["rigor_domain"] = dict(evidence["forge_domain"])
    refine = apply_skill_refinement(
        "pnl_target",
        evidence,
        settings=settings,
        enabled_flag="pnl_target",
    )
    return {
        **run,
        **refine,
        "job": "pnl_target",
        "evaluated": run.get("evaluated"),
        "next_target": run.get("next_target"),
    }

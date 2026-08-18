# -*- coding: utf-8
"""dsh-finance close checks → harness self-evolution (finance_close job)."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_finance import run_finance_close_checks
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def _finance_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("finance_close") or {})


def finance_close_to_harness_evidence(
    checks: dict[str, Any],
    *,
    portfolio_summary: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    risk = checks.get("risk") or {}
    reconcile = checks.get("reconcile") or {}
    variance = checks.get("variance") or {}
    snapshot = checks.get("reconcile_snapshot") or {}

    if risk.get("largest_position"):
        pos = risk["largest_position"]
        memory.append(f"最大持仓 {pos.get('name')} 占比 {float(pos.get('pct') or 0):.1f}%")
    if risk.get("cash_pct") is not None:
        memory.append(f"现金占比 {float(risk['cash_pct']):.1f}%")

    for flag in risk.get("flags") or []:
        memory.append(f"组合风控：{flag}")
        if "超过上限" in flag or "低于下限" in flag:
            policy.append(f"finance：{flag}，下日偏防御")
            plan.append("finance_close：审视仓位/现金纪律")

    if reconcile.get("reconciled"):
        memory.append(f"收盘对账通过（差 {float(reconcile.get('difference') or 0):+,.2f} 元）")
    else:
        for flag in reconcile.get("flags") or []:
            memory.append(f"对账：{flag}")
            playbook.append("收盘后核对 ledger / capital / 净值口径")
            plan.append("finance_close：补全入出金或 ledger 后再 refine")

    open_count = len(snapshot.get("open_items") or [])
    if open_count:
        memory.append(f"reconcile 未平项 {open_count} 条")
        buckets = snapshot.get("aging_buckets") or {}
        if buckets:
            memory.append(
                "账龄 "
                + " · ".join(f"{k}={v}" for k, v in buckets.items() if v)
            )
    for flag in snapshot.get("stale_flags") or []:
        memory.append(f"stale：{flag}")
        playbook.append("reconcile：清理 stale 未平项后再 sign-off")
        plan.append("finance_close：处理 stale open items")
    if snapshot.get("sign_off_ready"):
        memory.append("reconcile sign-off ready")

    if variance.get("material"):
        memory.append(
            f"净值变动 {float(variance.get('total_variance') or 0):+,.0f} 元 "
            f"（bridge 残差 {float(variance.get('residual') or 0):+,.2f}）"
        )
    elif variance.get("reconciled"):
        memory.append(f"variance bridge 闭合（残差 {float(variance.get('residual') or 0):+,.2f}）")

    for flag in variance.get("flags") or []:
        if "残差" in flag:
            playbook.append("finance：variance bridge 未闭合，优先核对 daily_pnl 与 capital")

    pf = portfolio_summary or {}
    if pf.get("daily_pnl") is not None:
        memory.append(f"当日盈亏 {float(pf['daily_pnl']):+,.0f}（finance_close 校验）")

    summary = "finance_close"
    if checks.get("passed"):
        summary += " pass"
    else:
        summary += f" block={len(checks.get('blocking_flags') or [])}"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
        "verification_signals": ["finance_close_pass"] if checks.get("passed") else ["finance_close_block"],
    }


def apply_finance_close_harness_refinement(
    portfolio_summary: Optional[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not portfolio_summary:
        return {"skipped": True, "reason": "no portfolio_summary", "job": "finance_close"}

    cfg = _finance_cfg(settings)
    if cfg.get("enabled") is False:
        return {"skipped": True, "reason": "finance_close disabled", "job": "finance_close"}

    checks = run_finance_close_checks(portfolio_summary, settings=settings)
    evidence = finance_close_to_harness_evidence(checks, portfolio_summary=portfolio_summary)
    evidence["forge_domain"] = {
        "portfolio_summary": portfolio_summary,
        "risk": checks.get("risk"),
        "reconcile": checks.get("reconcile"),
        "reconcile_snapshot": checks.get("reconcile_snapshot"),
        "variance": checks.get("variance"),
    }
    evidence["rigor_domain"] = {
        **evidence["forge_domain"],
        "portfolio_summary": portfolio_summary,
    }
    refine = apply_skill_refinement(
        "finance_close",
        evidence,
        settings=settings,
        enabled_flag="finance_close",
    )
    return {**refine, "job": "finance_close", "checks": checks}

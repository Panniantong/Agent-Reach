# -*- coding: utf-8
"""Weekly what-if sell rules → harness self-evolution for sell_ratio tuning."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement, merge_harness_evidence
from agent_reach.daily_run.sell_rules_whatif import (
    summarize_buy_whatif_for_harness,
    summarize_whatif_for_harness,
)
from agent_reach.daily_run.buy_rules_whatif_optimizer import optimize_buy_rules_whatif_with_deepseek
from agent_reach.daily_run.sell_rules_whatif_optimizer import optimize_sell_rules_whatif_with_deepseek
from agent_reach.daily_run.sell_threshold_optimizer import optimize_sell_threshold_with_deepseek


def whatif_report_to_harness_evidence(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build harness evidence from weekly report sell/buy what-if blocks."""
    whatif = report.get("sell_rules_whatif") or {}
    evidence = summarize_whatif_for_harness(
        whatif,
        weekly_pnl=report.get("weekly_pnl"),
        weekly_pnl_pct=report.get("weekly_pnl_pct"),
    )
    buy_whatif = report.get("buy_rules_whatif") or {}
    if buy_whatif and not buy_whatif.get("skipped"):
        buy_evidence = summarize_buy_whatif_for_harness(
            buy_whatif,
            weekly_pnl=report.get("weekly_pnl"),
            weekly_pnl_pct=report.get("weekly_pnl_pct"),
        )
        evidence = merge_harness_evidence(evidence, buy_evidence)
    evidence["rigor_domain"] = {
        "whatif": whatif,
        "buy_whatif": buy_whatif,
        "intraday_friction_whatif": report.get("intraday_friction_whatif"),
        "intraday_sell_whatif": report.get("intraday_sell_whatif"),
        "weekly_pnl": report.get("weekly_pnl"),
        "weekly_pnl_pct": report.get("weekly_pnl_pct"),
        "week_start": report.get("week_start"),
        "week_end": report.get("week_end"),
    }
    return evidence


def apply_sell_rules_whatif_harness_refinement(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Persist weekly what-if sell analysis into harness for sell_ratio evolution."""
    whatif = report.get("sell_rules_whatif") or {}
    if whatif.get("skipped"):
        return {
            "skipped": True,
            "reason": whatif.get("skip_reason") or "what-if skipped",
            "job": "sell_rules_whatif",
        }
    evidence = whatif_report_to_harness_evidence(report, settings=settings)
    llm_opt = optimize_sell_rules_whatif_with_deepseek(report, settings=settings)
    if not llm_opt.get("skipped") and llm_opt.get("evidence"):
        evidence = merge_harness_evidence(evidence, llm_opt["evidence"])
        evidence.setdefault("rigor_domain", {})
        if isinstance(evidence["rigor_domain"], dict):
            evidence["rigor_domain"]["llm_optimal"] = llm_opt.get("optimal")
            evidence["rigor_domain"]["llm_planner"] = llm_opt.get("planner")
    buy_llm_opt = optimize_buy_rules_whatif_with_deepseek(report, settings=settings)
    if not buy_llm_opt.get("skipped") and buy_llm_opt.get("evidence"):
        evidence = merge_harness_evidence(evidence, buy_llm_opt["evidence"])
        evidence.setdefault("rigor_domain", {})
        if isinstance(evidence["rigor_domain"], dict):
            evidence["rigor_domain"]["buy_llm_optimal"] = buy_llm_opt.get("optimal")
            evidence["rigor_domain"]["buy_llm_planner"] = buy_llm_opt.get("planner")
    sell_threshold_opt = optimize_sell_threshold_with_deepseek(report, settings=settings)
    if not sell_threshold_opt.get("skipped") and sell_threshold_opt.get("evidence"):
        evidence = merge_harness_evidence(evidence, sell_threshold_opt["evidence"])
        evidence.setdefault("rigor_domain", {})
        if isinstance(evidence["rigor_domain"], dict):
            evidence["rigor_domain"]["sell_threshold_llm_optimal"] = sell_threshold_opt.get("optimal")
    result = apply_skill_refinement(
        "sell_rules_whatif",
        evidence,
        settings=settings,
        enabled_flag="harness",
    )
    if not llm_opt.get("skipped"):
        result["llm_optimize"] = {
            "skipped": False,
            "planner": llm_opt.get("planner"),
            "optimal": llm_opt.get("optimal"),
            "provider": llm_opt.get("provider"),
        }
    else:
        result["llm_optimize"] = {"skipped": True, "reason": llm_opt.get("reason")}
    if not buy_llm_opt.get("skipped"):
        result["buy_llm_optimize"] = {
            "skipped": False,
            "planner": buy_llm_opt.get("planner"),
            "optimal": buy_llm_opt.get("optimal"),
            "provider": buy_llm_opt.get("provider"),
        }
    else:
        result["buy_llm_optimize"] = {"skipped": True, "reason": buy_llm_opt.get("reason")}
    if not sell_threshold_opt.get("skipped"):
        result["sell_threshold_llm_optimize"] = {
            "skipped": False,
            "planner": sell_threshold_opt.get("planner"),
            "optimal": sell_threshold_opt.get("optimal"),
            "provider": sell_threshold_opt.get("provider"),
        }
    else:
        result["sell_threshold_llm_optimize"] = {
            "skipped": True,
            "reason": sell_threshold_opt.get("reason"),
        }
    return result

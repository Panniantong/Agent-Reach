# -*- coding: utf-8
"""Intraday sell scan replay what-if → harness self-evolution."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement, merge_harness_evidence
from agent_reach.daily_run.intraday_sell_whatif_optimizer import optimize_intraday_sell_with_deepseek
from agent_reach.daily_run.sell_rules_whatif import summarize_intraday_sell_for_harness


def _intraday_sell_whatif_block(source: dict[str, Any]) -> dict[str, Any]:
    return dict(source.get("intraday_sell_whatif") or {})


def intraday_sell_whatif_to_harness_evidence(
    whatif: dict[str, Any],
    *,
    scope: str = "daily",
) -> dict[str, Any]:
    evidence = summarize_intraday_sell_for_harness(whatif)
    evidence["rigor_domain"] = {
        "intraday_sell_whatif": whatif,
        "scope": scope,
    }
    return evidence


def _apply_intraday_sell_refinement(
    source: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    scope: str = "daily",
    rigor_extras: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    whatif = _intraday_sell_whatif_block(source)
    if whatif.get("skipped"):
        return {
            "skipped": True,
            "reason": whatif.get("skip_reason") or "intraday sell what-if skipped",
            "job": "intraday_sell",
        }

    evidence = intraday_sell_whatif_to_harness_evidence(whatif, scope=scope)
    if rigor_extras and isinstance(evidence.get("rigor_domain"), dict):
        evidence["rigor_domain"].update(rigor_extras)

    llm_opt = optimize_intraday_sell_with_deepseek(source, settings=settings)
    if not llm_opt.get("skipped") and llm_opt.get("evidence"):
        evidence = merge_harness_evidence(evidence, llm_opt["evidence"])
        if isinstance(evidence.get("rigor_domain"), dict):
            evidence["rigor_domain"]["llm_optimal"] = llm_opt.get("optimal")

    result = apply_skill_refinement("intraday_sell", evidence, settings=settings)
    if not llm_opt.get("skipped"):
        result["llm_optimize"] = {
            "skipped": False,
            "planner": llm_opt.get("planner"),
            "optimal": llm_opt.get("optimal"),
            "provider": llm_opt.get("provider"),
        }
    else:
        result["llm_optimize"] = {"skipped": True, "reason": llm_opt.get("reason")}
    return result


def apply_intraday_sell_harness_refinement(
    portfolio_summary: Optional[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Persist close-day intraday sell scan replay into harness."""
    if not portfolio_summary:
        return {"skipped": True, "reason": "no portfolio_summary", "job": "intraday_sell"}

    return _apply_intraday_sell_refinement(
        portfolio_summary,
        settings=settings,
        scope="daily",
    )


def apply_weekly_intraday_sell_harness_refinement(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Persist weekly intraday sell scan replay aggregate into harness."""
    if not report:
        return {"skipped": True, "reason": "no weekly report", "job": "intraday_sell"}

    return _apply_intraday_sell_refinement(
        report,
        settings=settings,
        scope="weekly",
        rigor_extras={
            "week_start": report.get("week_start"),
            "week_end": report.get("week_end"),
        },
    )

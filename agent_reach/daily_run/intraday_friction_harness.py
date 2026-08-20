# -*- coding: utf-8
"""Close / weekly intraday friction/trend what-if → harness self-evolution."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.friction_model_optimizer import optimize_friction_model_with_deepseek
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement, merge_harness_evidence
from agent_reach.daily_run.intraday_whatif_optimizer import optimize_intraday_friction_with_deepseek
from agent_reach.daily_run.intraday_trends_optimizer import optimize_intraday_trends_with_deepseek
from agent_reach.daily_run.sell_rules_whatif import summarize_intraday_friction_for_harness


def _intraday_friction_whatif_block(source: dict[str, Any]) -> dict[str, Any]:
    return dict(source.get("intraday_friction_whatif") or {})


def _llm_payload_from_whatif(
    whatif: dict[str, Any],
    *,
    as_of: Any = None,
) -> dict[str, Any]:
    return {
        "as_of": as_of or whatif.get("as_of"),
        "intraday_friction_whatif": whatif,
    }


def _apply_intraday_friction_refinement(
    whatif: dict[str, Any],
    *,
    llm_payload: dict[str, Any],
    settings: Optional[dict[str, Any]] = None,
    scope: str = "daily",
    rigor_extras: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if whatif.get("skipped"):
        return {
            "skipped": True,
            "reason": whatif.get("skip_reason") or "intraday friction what-if skipped",
            "job": "intraday_friction",
        }

    evidence = summarize_intraday_friction_for_harness(whatif)
    rigor_domain: dict[str, Any] = {"intraday_friction_whatif": whatif, "scope": scope}
    if rigor_extras:
        rigor_domain.update(rigor_extras)
    evidence["rigor_domain"] = rigor_domain
    llm_opt = optimize_intraday_friction_with_deepseek(llm_payload, settings=settings)
    if not llm_opt.get("skipped") and llm_opt.get("evidence"):
        evidence = merge_harness_evidence(evidence, llm_opt["evidence"])
        if isinstance(evidence.get("rigor_domain"), dict):
            evidence["rigor_domain"]["llm_optimal"] = llm_opt.get("optimal")
    model_opt = optimize_friction_model_with_deepseek(llm_payload, settings=settings)
    if not model_opt.get("skipped") and model_opt.get("evidence"):
        evidence = merge_harness_evidence(evidence, model_opt["evidence"])
        if isinstance(evidence.get("rigor_domain"), dict):
            evidence["rigor_domain"]["friction_model_llm_optimal"] = model_opt.get("optimal")
    trends_opt = optimize_intraday_trends_with_deepseek(llm_payload, settings=settings)
    if not trends_opt.get("skipped") and trends_opt.get("evidence"):
        evidence = merge_harness_evidence(evidence, trends_opt["evidence"])
        if isinstance(evidence.get("rigor_domain"), dict):
            evidence["rigor_domain"]["trends_llm_optimal"] = trends_opt.get("optimal")
    result = apply_skill_refinement("intraday_friction", evidence, settings=settings)
    if not llm_opt.get("skipped"):
        result["llm_optimize"] = {
            "skipped": False,
            "planner": llm_opt.get("planner"),
            "optimal": llm_opt.get("optimal"),
            "provider": llm_opt.get("provider"),
        }
    else:
        result["llm_optimize"] = {"skipped": True, "reason": llm_opt.get("reason")}
    if not model_opt.get("skipped"):
        result["friction_model_llm_optimize"] = {
            "skipped": False,
            "planner": model_opt.get("planner"),
            "optimal": model_opt.get("optimal"),
            "provider": model_opt.get("provider"),
        }
    else:
        result["friction_model_llm_optimize"] = {"skipped": True, "reason": model_opt.get("reason")}
    if not trends_opt.get("skipped"):
        result["trends_llm_optimize"] = {
            "skipped": False,
            "planner": trends_opt.get("planner"),
            "optimal": trends_opt.get("optimal"),
            "provider": trends_opt.get("provider"),
        }
    else:
        result["trends_llm_optimize"] = {"skipped": True, "reason": trends_opt.get("reason")}
    return result


def apply_intraday_friction_harness_refinement(
    portfolio_summary: Optional[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not portfolio_summary:
        return {"skipped": True, "reason": "no portfolio_summary", "job": "intraday_friction"}

    whatif = _intraday_friction_whatif_block(portfolio_summary)
    return _apply_intraday_friction_refinement(
        whatif,
        llm_payload=portfolio_summary,
        settings=settings,
        scope="daily",
    )


def apply_weekly_intraday_friction_harness_refinement(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not report:
        return {"skipped": True, "reason": "no weekly report", "job": "intraday_friction"}

    whatif = _intraday_friction_whatif_block(report)
    llm_payload = _llm_payload_from_whatif(whatif, as_of=report.get("week_end"))
    return _apply_intraday_friction_refinement(
        whatif,
        llm_payload=llm_payload,
        settings=settings,
        scope="weekly",
        rigor_extras={
            "week_start": report.get("week_start"),
            "week_end": report.get("week_end"),
        },
    )

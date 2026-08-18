# -*- coding: utf-8
"""Shared helpers for daily-run harness skill runtimes."""

from __future__ import annotations

from typing import Any, Optional

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger("agent_reach.daily_run.harness_skill")


def merge_harness_evidence(*parts: dict[str, Any]) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []
    summaries: list[str] = []
    seen: set[str] = set()

    def _add(kind: str, line: str) -> None:
        text = str(line or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        bucket = {"memory": memory, "policy": policy, "playbook": playbook, "plan": plan}[kind]
        bucket.append(text)

    for part in parts:
        if not part:
            continue
        for line in part.get("memory") or []:
            _add("memory", line)
        for line in part.get("policy") or []:
            _add("policy", line)
        for line in part.get("playbook") or []:
            _add("playbook", line)
        for line in part.get("plan") or []:
            _add("plan", line)
        if part.get("summary"):
            summaries.append(str(part["summary"]))

    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": " | ".join(summaries) if summaries else "harness_skill",
    }


def apply_skill_refinement(
    job: str,
    evidence: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    enabled_flag: Optional[str] = None,
) -> dict[str, Any]:
    """Persist harness evidence unless disabled via harness.jobs or section flag."""
    from agent_reach.daily_run.harness import refine_after_job
    from agent_reach.daily_run.settings import load_settings

    cfg = settings or load_settings()
    harness_cfg = cfg.get("harness") or {}
    if harness_cfg.get("enabled") is False:
        return {"skipped": True, "reason": "harness disabled", "job": job}

    if enabled_flag:
        section = cfg.get(enabled_flag) or {}
        if section.get("harness_evolve", True) is False:
            return {"skipped": True, "reason": f"{enabled_flag}.harness_evolve disabled", "job": job}

    if not any(evidence.get(k) for k in ("memory", "policy", "playbook", "plan")):
        return {"skipped": True, "reason": "empty evidence", "job": job}

    from agent_reach.daily_run.harness_forge_gates import (
        evaluate_forge_gate,
        strip_forge_domain,
    )

    forge = evaluate_forge_gate(job, evidence, settings=cfg)
    if forge is not None and not forge.passed:
        from agent_reach.daily_run.harness_apply_gate import record_apply_audit

        record_apply_audit(
            job=job,
            status="skipped",
            reason="forge_gate_failed",
            layer="a",
            forge_gate=forge.to_dict(),
            changes=0,
        )
        return {
            "skipped": True,
            "reason": "forge_gate_failed",
            "job": job,
            "forge_gate": forge.to_dict(),
        }

    result = refine_after_job(job, evidence=strip_forge_domain(evidence), settings=cfg)
    if forge is not None:
        result["forge_gate"] = forge.to_dict()
    result["job"] = job
    if not result.get("skipped"):
        try:
            from agent_reach.daily_run.harness import refine_after_job_llm_summarize

            summarize = refine_after_job_llm_summarize(
                job,
                evidence=evidence,
                settings=cfg,
                layer_a_result=result,
            )
            if summarize:
                result["llm_summarize"] = summarize
        except Exception as exc:
            logger.warning("daily-run harness llm_summarize failed ({}): {}", job, exc)
    return result


def effective_overlay_snapshot(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    from agent_reach.daily_run.settings import effective_settings, load_settings

    cfg = effective_settings(settings or load_settings())
    runtime = dict(cfg.get("harness_runtime") or {})
    return {
        "threshold_overlay": runtime.get("threshold_overlay"),
        "runtime_overlay": runtime.get("runtime_overlay"),
        "forecast_overlay": runtime.get("forecast_overlay"),
        "lookback_overlay": runtime.get("lookback_overlay"),
        "trade_signals": runtime.get("trade_signals"),
    }

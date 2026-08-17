# -*- coding: utf-8
"""Orchestrate weekly-phase harness skills (skill_closure / run_guard / residual layer_a)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import effective_overlay_snapshot
from agent_reach.daily_run.settings import effective_settings, load_settings


@dataclass
class WeeklyHarnessSkillsReport:
    run_guard: dict[str, Any] = field(default_factory=dict)
    weekly_layer_a: dict[str, Any] = field(default_factory=dict)
    effective_overlay: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_guard": self.run_guard,
            "weekly_layer_a": self.weekly_layer_a,
            "effective_overlay": self.effective_overlay,
            "total_changes": sum(
                int((block or {}).get("changes") or 0)
                for block in (self.run_guard, self.weekly_layer_a)
                if not (block or {}).get("skipped")
            ),
        }


def _job_enabled(cfg: dict[str, Any], job: str) -> bool:
    jobs = cfg.get("jobs") or {}
    if isinstance(jobs, dict) and job in jobs:
        return bool(jobs[job])
    return True


def run_weekly_harness_refinements(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    skip_run_guard: bool = False,
) -> WeeklyHarnessSkillsReport:
    """Run run_guard harness when skill_closure is off (schedule gaps subset)."""
    cfg = effective_settings(settings or load_settings())
    harness_cfg = cfg.get("harness") or {}
    out = WeeklyHarnessSkillsReport()

    if (
        not skip_run_guard
        and _job_enabled(harness_cfg, "run_guard")
        and not _job_enabled(harness_cfg, "skill_closure")
    ):
        from agent_reach.daily_run.run_guard_harness import apply_process_improvements_guard_harness

        out.run_guard = apply_process_improvements_guard_harness(
            report.get("process_improvements") or [],
            settings=cfg,
        )

    out.effective_overlay = effective_overlay_snapshot(cfg)
    return out


def run_weekly_layer_a_refinement(
    weekly_evidence: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Residual weekly job refine (PnL / snippets / applied_config when specialized jobs on)."""
    from agent_reach.daily_run.harness import refine_after_job

    cfg = effective_settings(settings or load_settings())
    harness_cfg = cfg.get("harness") or {}
    if harness_cfg.get("enabled") is False:
        return {"skipped": True, "reason": "harness disabled", "job": "weekly"}
    if not _job_enabled(harness_cfg, "weekly"):
        return {"skipped": True, "reason": "job weekly disabled in harness.jobs", "job": "weekly"}

    return refine_after_job("weekly", evidence=weekly_evidence, settings=cfg)

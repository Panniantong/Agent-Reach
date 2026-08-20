# -*- coding: utf-8
"""Orchestrate weekly-phase harness skills (skill_closure / run_guard / residual layer_a)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import effective_overlay_snapshot
from agent_reach.daily_run.settings import effective_settings, load_settings


@dataclass
class WeeklyHarnessSkillsReport:
    finance_variance: dict[str, Any] = field(default_factory=dict)
    finance_statements: dict[str, Any] = field(default_factory=dict)
    finance_research: dict[str, Any] = field(default_factory=dict)
    finance_close_plan: dict[str, Any] = field(default_factory=dict)
    expert_consensus_weekly: dict[str, Any] = field(default_factory=dict)
    run_guard: dict[str, Any] = field(default_factory=dict)
    sell_rules_whatif: dict[str, Any] = field(default_factory=dict)
    harness_threshold: dict[str, Any] = field(default_factory=dict)
    intraday_friction: dict[str, Any] = field(default_factory=dict)
    intraday_sell: dict[str, Any] = field(default_factory=dict)
    weekly_layer_a: dict[str, Any] = field(default_factory=dict)
    effective_overlay: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finance_variance": self.finance_variance,
            "finance_statements": self.finance_statements,
            "finance_research": self.finance_research,
            "finance_close_plan": self.finance_close_plan,
            "expert_consensus_weekly": self.expert_consensus_weekly,
            "run_guard": self.run_guard,
            "sell_rules_whatif": self.sell_rules_whatif,
            "harness_threshold": self.harness_threshold,
            "intraday_friction": self.intraday_friction,
            "intraday_sell": self.intraday_sell,
            "weekly_layer_a": self.weekly_layer_a,
            "effective_overlay": self.effective_overlay,
            "total_changes": sum(
                int((block or {}).get("changes") or 0)
                for block in (
                    self.finance_variance,
                    self.finance_statements,
                    self.finance_research,
                    self.finance_close_plan,
                    self.expert_consensus_weekly,
                    self.run_guard,
                    self.sell_rules_whatif,
                    self.harness_threshold,
                    self.intraday_friction,
                    self.intraday_sell,
                    self.weekly_layer_a,
                )
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
    skill_writeback: Optional[dict[str, Any]] = None,
) -> WeeklyHarnessSkillsReport:
    """Run weekly finance harness jobs and run_guard when skill_closure is off."""
    cfg = effective_settings(settings or load_settings())
    harness_cfg = cfg.get("harness") or {}
    out = WeeklyHarnessSkillsReport()

    if _job_enabled(harness_cfg, "finance_variance"):
        from agent_reach.daily_run.finance_variance_harness import apply_finance_variance_harness_refinement

        out.finance_variance = apply_finance_variance_harness_refinement(report, settings=cfg)

    if _job_enabled(harness_cfg, "finance_statements"):
        from agent_reach.daily_run.finance_statements_harness import (
            apply_finance_statements_harness_refinement,
        )

        out.finance_statements = apply_finance_statements_harness_refinement(report, settings=cfg)

    if _job_enabled(harness_cfg, "finance_research"):
        from agent_reach.daily_run.finance_research_harness import apply_finance_research_harness_refinement

        out.finance_research = apply_finance_research_harness_refinement(report, settings=cfg)

    if _job_enabled(harness_cfg, "finance_close_plan"):
        from agent_reach.daily_run.finance_close_plan_harness import apply_finance_close_plan_harness_refinement

        out.finance_close_plan = apply_finance_close_plan_harness_refinement(
            report,
            settings=cfg,
            skill_writeback=skill_writeback,
        )

    if _job_enabled(harness_cfg, "expert_consensus_weekly"):
        from agent_reach.daily_run.expert_consensus_weekly_harness import (
            apply_expert_consensus_weekly_harness_refinement,
        )

        out.expert_consensus_weekly = apply_expert_consensus_weekly_harness_refinement(
            report,
            settings=cfg,
        )

    if _job_enabled(harness_cfg, "sell_rules_whatif"):
        from agent_reach.daily_run.sell_rules_whatif_harness import (
            apply_sell_rules_whatif_harness_refinement,
        )

        out.sell_rules_whatif = apply_sell_rules_whatif_harness_refinement(
            report,
            settings=cfg,
        )

    if _job_enabled(harness_cfg, "harness_threshold"):
        from agent_reach.daily_run.harness_evolution_optimizers import apply_weekly_harness_llm_refinement

        out.harness_threshold = apply_weekly_harness_llm_refinement(report, settings=cfg)

    if _job_enabled(harness_cfg, "intraday_friction"):
        from agent_reach.daily_run.intraday_friction_harness import (
            apply_weekly_intraday_friction_harness_refinement,
        )

        out.intraday_friction = apply_weekly_intraday_friction_harness_refinement(
            report,
            settings=cfg,
        )

    if _job_enabled(harness_cfg, "intraday_sell"):
        from agent_reach.daily_run.intraday_sell_harness import (
            apply_weekly_intraday_sell_harness_refinement,
        )

        out.intraday_sell = apply_weekly_intraday_sell_harness_refinement(
            report,
            settings=cfg,
        )

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

# -*- coding: utf-8
"""Orchestrate close-phase harness skills (verify / improve / audit)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agent_reach.daily_run.auditor import AuditResult
from agent_reach.daily_run.close_improvements import CloseImprovements
from agent_reach.daily_run.harness_skill_base import effective_overlay_snapshot
from agent_reach.daily_run.settings import effective_settings, load_settings


@dataclass
class CloseHarnessSkillsReport:
    verify: dict[str, Any] = field(default_factory=dict)
    close_improve: dict[str, Any] = field(default_factory=dict)
    data_audit: dict[str, Any] = field(default_factory=dict)
    watchlist_adjust: dict[str, Any] = field(default_factory=dict)
    close_layer_a: dict[str, Any] = field(default_factory=dict)
    effective_overlay: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verify": self.verify,
            "close_improve": self.close_improve,
            "data_audit": self.data_audit,
            "watchlist_adjust": self.watchlist_adjust,
            "close_layer_a": self.close_layer_a,
            "effective_overlay": self.effective_overlay,
            "total_changes": sum(
                int((block or {}).get("changes") or 0)
                for block in (
                    self.verify,
                    self.close_improve,
                    self.data_audit,
                    self.watchlist_adjust,
                    self.close_layer_a,
                )
                if not (block or {}).get("skipped")
            ),
        }


def run_close_harness_refinements(
    *,
    verify: dict[str, Any],
    improvements: Optional[CloseImprovements] = None,
    audit: Optional[AuditResult | dict[str, Any]] = None,
    forecast_review: Optional[dict[str, Any]] = None,
    watchlist_adjust: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> CloseHarnessSkillsReport:
    """Run verify / close_improve / data_audit harness refinements after close."""
    cfg = effective_settings(settings or load_settings())
    report = CloseHarnessSkillsReport()

    from agent_reach.daily_run.verify_harness import apply_verify_harness_refinement

    report.verify = apply_verify_harness_refinement(
        verify,
        settings=cfg,
        forecast_review=forecast_review,
    )

    if improvements is not None and improvements.items:
        from agent_reach.daily_run.close_improve_harness import apply_close_improve_harness_refinement

        report.close_improve = apply_close_improve_harness_refinement(
            improvements,
            settings=cfg,
            forecast_review=forecast_review,
        )

    if audit is not None:
        from agent_reach.daily_run.data_audit_harness import apply_data_audit_harness_refinement

        report.data_audit = apply_data_audit_harness_refinement(audit, settings=cfg)

    if watchlist_adjust is not None:
        from agent_reach.daily_run.watchlist_adjust_harness import apply_watchlist_adjust_harness_refinement

        report.watchlist_adjust = apply_watchlist_adjust_harness_refinement(
            watchlist_adjust,
            settings=cfg,
        )

    report.effective_overlay = effective_overlay_snapshot(cfg)
    return report


def run_close_layer_a_refinement(
    close_evidence: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Residual close job refine (portfolio PnL only when specialized jobs enabled)."""
    from agent_reach.daily_run.harness import refine_after_job

    cfg = effective_settings(settings or load_settings())
    harness_cfg = cfg.get("harness") or {}
    if harness_cfg.get("enabled") is False:
        return {"skipped": True, "reason": "harness disabled", "job": "close"}
    jobs = harness_cfg.get("jobs") or {}
    if isinstance(jobs, dict) and jobs.get("close") is False:
        return {"skipped": True, "reason": "job close disabled in harness.jobs", "job": "close"}

    return refine_after_job("close", evidence=close_evidence, settings=cfg)

# -*- coding: utf-8
"""Orchestrate forecast-phase harness skills."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import effective_overlay_snapshot
from agent_reach.daily_run.settings import effective_settings, load_settings


@dataclass
class ForecastHarnessSkillsReport:
    forecast_calibrate: dict[str, Any] = field(default_factory=dict)
    finance_research: dict[str, Any] = field(default_factory=dict)
    forecast_layer_a: dict[str, Any] = field(default_factory=dict)
    effective_overlay: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "forecast_calibrate": self.forecast_calibrate,
            "finance_research": self.finance_research,
            "forecast_layer_a": self.forecast_layer_a,
            "effective_overlay": self.effective_overlay,
            "total_changes": sum(
                int((block or {}).get("changes") or 0)
                for block in (self.forecast_calibrate, self.finance_research, self.forecast_layer_a)
                if not (block or {}).get("skipped")
            ),
        }


def run_forecast_harness_refinements(
    forecast: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> ForecastHarnessSkillsReport:
    cfg = effective_settings(settings or load_settings())
    report = ForecastHarnessSkillsReport()

    from agent_reach.daily_run.forecast_calibrate_harness import apply_forecast_calibrate_harness_refinement
    from agent_reach.daily_run.forecast_interval_policy import should_trigger_forecast_calibrate

    accuracy_trigger = should_trigger_forecast_calibrate(cfg)
    report.forecast_calibrate = apply_forecast_calibrate_harness_refinement(forecast, settings=cfg)
    if accuracy_trigger and isinstance(report.forecast_calibrate, dict):
        report.forecast_calibrate["accuracy_guard_trigger"] = True
        notes = list(report.forecast_calibrate.get("optimization_notes") or [])
        notes.insert(
            0,
            "准确率连续低于阈值，已自动触发 forecast_calibrate（P3 accuracy guard）",
        )
        report.forecast_calibrate["optimization_notes"] = notes

    harness_cfg = cfg.get("harness") or {}
    jobs = harness_cfg.get("jobs") or {}
    weekly_cfg = cfg.get("weekly_report") or {}
    wf_cfg = cfg.get("week_forecast") or {}
    skip_finance = (
        bool(wf_cfg.get("skip_finance_research_if_weekly_digest", False))
        and weekly_cfg.get("enabled", True) is not False
    )
    if skip_finance:
        from agent_reach.daily_run.weekly_digest import load_weekly_digest

        skip_finance = bool(load_weekly_digest())

    if not isinstance(jobs, dict) or jobs.get("finance_research", True) is not False:
        if skip_finance:
            report.finance_research = {
                "skipped": True,
                "reason": "weekly digest available; finance_research deferred to Saturday",
            }
        else:
            fr_cfg = cfg.get("finance_research") or {}
            if fr_cfg.get("run_on_forecast", True) is not False:
                from agent_reach.daily_run.finance_research_harness import (
                    apply_finance_research_harness_refinement,
                )

                report.finance_research = apply_finance_research_harness_refinement(
                    {"week_start": forecast.get("week_start"), "week_end": forecast.get("week_end")},
                    settings=cfg,
                    forecast=forecast,
                )

    report.effective_overlay = effective_overlay_snapshot(cfg)
    return report


def run_forecast_layer_a_refinement(
    forecast_evidence: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from agent_reach.daily_run.harness import refine_after_job

    cfg = effective_settings(settings or load_settings())
    harness_cfg = cfg.get("harness") or {}
    if harness_cfg.get("enabled") is False:
        return {"skipped": True, "reason": "harness disabled", "job": "forecast"}
    jobs = harness_cfg.get("jobs") or {}
    if isinstance(jobs, dict) and jobs.get("forecast") is False:
        return {"skipped": True, "reason": "job forecast disabled", "job": "forecast"}

    return refine_after_job("forecast", evidence=forecast_evidence, settings=cfg)

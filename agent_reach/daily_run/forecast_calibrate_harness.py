# -*- coding: utf-8
"""Week forecast calibration / MSS paths → harness (forecast layer_a dedupe)."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def forecast_to_harness_evidence(forecast: dict[str, Any]) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    ws = forecast.get("week_start") or ""
    we = forecast.get("week_end") or ""
    memory.append(f"forecast 窗口 {ws}~{we}")

    cal = forecast.get("calibration_used") or {}
    if cal:
        vol = cal.get("vol_scale")
        bias = cal.get("bias_pct")
        if vol is not None:
            memory.append(f"forecast 校准 vol_scale={float(vol):.2f} bias={bias}")
        playbook.append(f"forecast 使用 calibration vol_scale={cal.get('vol_scale')}")

    mss_daily = forecast.get("mss_daily") or {}
    if isinstance(mss_daily, dict) and mss_daily.get("summary"):
        memory.append(str(mss_daily["summary"])[:200])
    for note in forecast.get("notes") or []:
        text = str(note)[:200]
        memory.append(text)
        if "MSS" in text and ("偏离" in text or "预测" in text):
            memory.append("MSS 预测偏离：下日调低进攻阈值或缩窄仓位")
            playbook.append("增大 mss_forecast.base_spread 或运行 daily-run optimize")
            plan.append("forecast_calibrate：校准 base_spread / vol_multiplier")

    summary = f"forecast_calibrate {ws}~{we} notes={len(forecast.get('notes') or [])}"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def apply_forecast_calibrate_harness_refinement(
    forecast: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    evidence = forecast_to_harness_evidence(forecast)
    wf_cfg = (settings or {}).get("week_forecast") or {}
    if wf_cfg.get("harness_evolve", True) is False:
        return {"skipped": True, "reason": "week_forecast.harness_evolve disabled", "job": "forecast_calibrate"}
    return apply_skill_refinement("forecast_calibrate", evidence, settings=settings)

# -*- coding: utf-8
"""Tiered macro MSS defense caps (P2)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional


def macro_defense_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    raw = dict((settings or {}).get("macro_defense_tiers") or {})
    return {
        "enabled": raw.get("enabled", True) is not False,
        "severe_mss": float(raw.get("severe_mss") or 30.0),
        "mild_mss": float(raw.get("mild_mss") or 40.0),
        "severe_max_position_pct": float(raw.get("severe_max_position_pct") or 40.0),
        "mild_max_position_pct": float(raw.get("mild_max_position_pct") or 60.0),
        "severe_deploy_ratio_cap": float(raw.get("severe_deploy_ratio_cap") or 0.25),
        "mild_deploy_ratio_cap": float(raw.get("mild_deploy_ratio_cap") or 0.45),
        "observe_weekly_trigger_max": max(1, int(raw.get("observe_weekly_trigger_max") or 3)),
        "observe_bump_to_mild": float(raw.get("observe_bump_to_mild") or 35.0),
    }


def apply_macro_defense_tiers(
    merged: dict[str, float],
    *,
    mss: Optional[float],
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Cap deploy_ratio / max_position_pct by MSS tier."""
    cfg = macro_defense_cfg(settings)
    if not cfg["enabled"] or mss is None:
        return {"applied": False}
    score = float(mss)
    notes: list[str] = []
    if score < cfg["severe_mss"]:
        merged["macro_veto"] = min(float(merged.get("macro_veto", 40.0)), cfg["severe_mss"])
        merged["max_position_pct"] = min(
            float(merged.get("max_position_pct", 35.0)),
            cfg["severe_max_position_pct"],
        )
        merged["deploy_ratio"] = min(
            float(merged.get("deploy_ratio", 1.0)),
            cfg["severe_deploy_ratio_cap"],
        )
        notes.append(f"MSS {score:.0f}<{cfg['severe_mss']:.0f} 全面防御")
        return {"applied": True, "tier": "severe", "notes": notes}
    if score < cfg["mild_mss"]:
        merged["macro_veto"] = min(float(merged.get("macro_veto", 40.0)), cfg["mild_mss"])
        merged["max_position_pct"] = min(
            float(merged.get("max_position_pct", 35.0)),
            cfg["mild_max_position_pct"],
        )
        merged["deploy_ratio"] = min(
            float(merged.get("deploy_ratio", 1.0)),
            cfg["mild_deploy_ratio_cap"],
        )
        notes.append(f"MSS {score:.0f}<{cfg['mild_mss']:.0f} 轻度防御")
        return {"applied": True, "tier": "mild", "notes": notes}
    return {"applied": False, "tier": "normal"}


def _runs_root() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "runs"


def min_lookback_mss_for_trading_day(trading_date: date | str) -> Optional[float]:
    """Minimum lookback MSS seen in saved intraday/close runs for a day."""
    ds = trading_date.isoformat() if isinstance(trading_date, date) else str(trading_date)[:10]
    runs_dir = _runs_root() / ds
    if not runs_dir.is_dir():
        return None
    mins: list[float] = []
    for path in runs_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        root = payload.get("payload") or payload
        for row in root.get("symbol_results") or []:
            if not isinstance(row, dict):
                continue
            trade = (row.get("result") or {}).get("trade") or {}
            decision = trade.get("decision") or {}
            if decision.get("lookback_mss") is not None:
                mins.append(float(decision["lookback_mss"]))
            for item in trade.get("trades") or []:
                if isinstance(item, dict) and item.get("lookback_mss") is not None:
                    mins.append(float(item["lookback_mss"]))
    return min(mins) if mins else None


def count_severe_tier_days(
    week_start: date | str,
    week_end: date | str,
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Count trading days whose session min lookback MSS fell below severe_mss."""
    cfg = macro_defense_cfg(settings)
    start = date.fromisoformat(str(week_start)[:10])
    end = date.fromisoformat(str(week_end)[:10])
    severe_days: list[str] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            low = min_lookback_mss_for_trading_day(cursor)
            if low is not None and low < cfg["severe_mss"]:
                severe_days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return {
        "severe_mss": cfg["severe_mss"],
        "severe_day_count": len(severe_days),
        "severe_days": severe_days,
    }


def build_weekly_observe_bump_evidence(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Layer-A evidence when severe tier fired often enough to relax macro_veto."""
    cfg = macro_defense_cfg(settings)
    if not cfg["enabled"]:
        return {"skipped": True, "reason": "macro_defense_tiers disabled"}

    week_start = report.get("week_start")
    week_end = report.get("week_end")
    if not week_start or not week_end:
        return {"skipped": True, "reason": "missing week range"}

    stats = count_severe_tier_days(week_start, week_end, settings=settings)
    count = int(stats["severe_day_count"])
    if count < cfg["observe_weekly_trigger_max"]:
        return {
            "skipped": True,
            "reason": "severe tier below observe threshold",
            "severe_day_count": count,
            "observe_weekly_trigger_max": cfg["observe_weekly_trigger_max"],
        }

    from agent_reach.daily_run.harness_policy import macro_veto_default, threshold_default

    base_veto = float(threshold_default(settings or {}, "macro_veto"))
    current = float(macro_veto_default(settings or {}))
    bump = float(cfg["observe_bump_to_mild"])
    if current >= bump - 0.01:
        return {
            "skipped": True,
            "reason": "macro_veto already at or above observe bump",
            "current_macro_veto": current,
            "observe_bump_to_mild": bump,
        }
    target = bump

    return {
        "memory": [
            (
                f"宏观severe tier 本周 {count} 天 MSS<{cfg['severe_mss']:.0f} "
                f"（{', '.join(stats['severe_days'][:4])}），"
                f"观察期上调 macro_veto {current:.0f}→{target:.0f}"
            )
        ],
        "policy": [f"macro_veto: {current:.0f}→{target:.0f}（severe观察期，非扫描脚注计数）"],
        "playbook": [
            "宏观否决观察期：severe tier 周内触发≥"
            f"{cfg['observe_weekly_trigger_max']} 天后 macro_veto 上调至 {target:.0f}"
        ],
        "summary": f"macro_observe_bump severe_days={count} veto {current:.0f}→{target:.0f}",
        "severe_day_count": count,
        "severe_days": stats["severe_days"],
    }


def apply_weekly_observe_bump_refinement(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from agent_reach.daily_run.harness_skill_base import apply_skill_refinement

    evidence = build_weekly_observe_bump_evidence(report, settings=settings)
    if evidence.get("skipped"):
        return {**evidence, "job": "harness_threshold"}
    result = apply_skill_refinement("harness_threshold", evidence, settings=settings)
    result["observe_bump"] = {
        "severe_day_count": evidence.get("severe_day_count"),
        "severe_days": evidence.get("severe_days"),
    }
    return result

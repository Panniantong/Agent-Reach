# -*- coding: utf-8
"""Tiered macro MSS defense caps (P2)."""

from __future__ import annotations

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

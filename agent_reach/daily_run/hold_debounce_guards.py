# -*- coding: utf-8
"""Two-strike debounce for defensive_trim sells when Sunday plan says 持有."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.plan_invalidation import (
    hold_debounce_invalidated,
    symbol_operation_plan_text,
)
from agent_reach.daily_run.snapshot_builder import _normalize_code


def hold_debounce_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = settings or {}
    intraday = dict(cfg.get("intraday") or {})
    block = dict(intraday.get("defensive_trim") or {})
    raw = dict(block.get("hold_debounce") or {})
    from agent_reach.daily_run.harness_policy import hold_debounce_policy_default

    enabled = raw.get("enabled", True)
    return {
        "enabled": enabled is not False,
        "required_strikes": max(
            1,
            int(round(hold_debounce_policy_default(cfg, "required_strikes"))),
        ),
        "hold_sell_ratio_cap": max(
            0.01,
            min(1.0, float(hold_debounce_policy_default(cfg, "hold_sell_ratio_cap"))),
        ),
    }


def operation_plan_requires_hold_debounce(code: str, settings: Optional[dict[str, Any]] = None) -> bool:
    """True when Sunday plan is 持有 and not an explicit 减仓/清仓 plan."""
    cfg = hold_debounce_cfg(settings)
    if not cfg.get("enabled", True):
        return False
    from agent_reach.daily_run.week_open_overlay import load_week_open_overlay, week_open_overlay_active

    if not week_open_overlay_active(settings or {}):
        wo = load_week_open_overlay()
        if not wo or wo.get("enabled") is False:
            return False
    text = symbol_operation_plan_text(code, settings)
    if not text or "持有" not in text:
        return False
    if any(k in text for k in ("减仓", "清仓")):
        return False
    return True


def touch_week_open_hold_debounce(
    settings: dict[str, Any],
    code: str,
    *,
    allow_defensive: bool,
    strikes: dict[str, int],
    price: Optional[float] = None,
) -> tuple[Optional[str], Optional[float]]:
    """Update per-symbol strike counter; return (block_reason, sell_ratio_cap)."""
    norm = _normalize_code(code)
    if not norm:
        return None, None
    if not operation_plan_requires_hold_debounce(code, settings):
        return None, None

    invalidated, inv_reason = hold_debounce_invalidated(norm, price, settings=settings)
    if invalidated:
        strikes[norm] = 0
        return None, None

    if not allow_defensive:
        strikes[norm] = 0
        return None, None

    cfg = hold_debounce_cfg(settings)
    required = int(cfg["required_strikes"])
    count = int(strikes.get(norm, 0))
    if count < required:
        strikes[norm] = count + 1
        return (
            f"周日计划「持有」，defensive_trim 需连续 {required} 次 MSS 信号确认"
            f"（{strikes[norm]}/{required}）"
            + (f"；{inv_reason}" if inv_reason else ""),
            None,
        )
    return None, float(cfg["hold_sell_ratio_cap"])

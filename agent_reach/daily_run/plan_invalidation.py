# -*- coding: utf-8
"""Sunday plan stop / invalidation hooks for hold_debounce and cover policy."""

from __future__ import annotations

import re
from typing import Any, Optional

from agent_reach.daily_run.snapshot_builder import _normalize_code


def plan_invalidation_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    intraday = dict((settings or {}).get("intraday") or {})
    block = dict(intraday.get("defensive_trim") or {})
    raw = dict(block.get("hold_debounce") or {})
    return {
        "invalidate_below_plan_stop": raw.get("invalidate_below_plan_stop", True) is not False,
        "invalidate_below_forecast_low": raw.get("invalidate_below_forecast_low", False) is True,
    }


def symbol_operation_plan_text(code: str, settings: Optional[dict[str, Any]] = None) -> str:
    norm = _normalize_code(code)
    if not norm:
        return ""
    from agent_reach.daily_run.week_open_overlay import load_week_open_overlay

    wo = load_week_open_overlay()
    if wo:
        for plan in wo.get("operation_plans") or []:
            if _normalize_code(str(plan.get("code") or "")) == norm:
                return str(plan.get("operation_plan") or plan.get("action") or "")
    runtime = (settings or {}).get("harness_runtime") or {}
    week_open = runtime.get("week_open") or {}
    for plan in week_open.get("operation_plans") or []:
        if _normalize_code(str(plan.get("code") or "")) == norm:
            return str(plan.get("operation_plan") or plan.get("action") or "")
    return ""


def operation_plan_has_trim(code: str, settings: Optional[dict[str, Any]] = None) -> bool:
    text = symbol_operation_plan_text(code, settings)
    return bool(text and any(k in text for k in ("减仓", "清仓")))


def _parse_stop_from_plan_text(text: str) -> Optional[float]:
    if not text:
        return None
    match = re.search(r"止损\s*([\d.]+)", text)
    if match:
        return float(match.group(1))
    return None


def symbol_plan_stop_price(code: str, *, settings: Optional[dict[str, Any]] = None) -> Optional[float]:
    """Resolve plan stop from week_open text, then close baseline."""
    text = symbol_operation_plan_text(code, settings)
    stop = _parse_stop_from_plan_text(text)
    if stop is not None and stop > 0:
        return stop
    try:
        from agent_reach.daily_run.forecast_operation_matrix import _load_stop_loss

        return _load_stop_loss(code, settings=settings)
    except Exception:
        return None


def symbol_forecast_low_price(code: str, *, settings: Optional[dict[str, Any]] = None) -> Optional[float]:
    try:
        from agent_reach.daily_run.week_forecast import load_forecast

        forecast = load_forecast()
        if not forecast:
            return None
        sym = (forecast.get("symbols") or {}).get(_normalize_code(code)) or {}
        structured = forecast.get("structured_predictions") or {}
        for row in structured.get("symbols") or []:
            if _normalize_code(str(row.get("code") or "")) == _normalize_code(code):
                return _optional_float(row.get("price_low"))
        days = sym.get("days") or {}
        lows = [_optional_float((d or {}).get("price_low")) for d in days.values()]
        lows = [x for x in lows if x is not None]
        if lows:
            return min(lows)
    except Exception:
        return None
    return None


def hold_debounce_invalidated(
    code: str,
    price: Optional[float],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[bool, str]:
    """Return (invalidated, reason) when plan stop / forecast low breached."""
    cfg = plan_invalidation_cfg(settings)
    px = _optional_float(price)
    if px is None or px <= 0:
        return False, ""
    stop = symbol_plan_stop_price(code, settings=settings)
    if cfg["invalidate_below_plan_stop"] and stop is not None and px <= stop:
        return True, f"现价 {px:.2f} ≤ 计划止损 {stop:.2f}，hold_debounce 让位"
    if cfg["invalidate_below_forecast_low"]:
        low = symbol_forecast_low_price(code, settings=settings)
        if low is not None and px <= low:
            return True, f"现价 {px:.2f} ≤ 预测下沿 {low:.2f}，hold_debounce 让位"
    return False, ""


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

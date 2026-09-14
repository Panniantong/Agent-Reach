# -*- coding: utf-8
"""Deep-loss cover exemptions for defensive_trim / plan trim sells."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.plan_invalidation import operation_plan_has_trim
from agent_reach.daily_run.snapshot_builder import _normalize_code


def deep_loss_cover_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    raw = dict((settings or {}).get("pnl_overview") or {})
    return {
        "defensive_trim_exempt_cover": raw.get("defensive_trim_exempt_cover", True) is not False,
        "plan_trim_exempt_cover": raw.get("plan_trim_exempt_cover", True) is not False,
    }


def cover_exempt_for_sell(
    code: str,
    *,
    settings: Optional[dict[str, Any]] = None,
    sell_kind: Optional[str] = None,
) -> bool:
    cfg = deep_loss_cover_cfg(settings)
    norm = _normalize_code(code)
    if sell_kind == "defensive_trim" and cfg["defensive_trim_exempt_cover"]:
        return True
    if cfg["plan_trim_exempt_cover"] and operation_plan_has_trim(norm, settings):
        return True
    return False

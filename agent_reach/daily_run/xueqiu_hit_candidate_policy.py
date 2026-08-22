# -*- coding: utf-8
"""Runtime overlay: tune hot-stock candidate weights from Xueqiu hit-rate stats."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

from agent_reach.daily_run.xueqiu_hit_outcomes import (
    summarize_xueqiu_hit_outcomes,
    xueqiu_hit_outcomes_enabled,
)


def xueqiu_hit_candidate_overlay_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    cfg = settings or {}
    macro = cfg.get("macro_collector") or {}
    nested = macro.get("xueqiu_hit_outcomes") or {}
    if nested.get("candidate_overlay_enabled") is False:
        return False
    if macro.get("xueqiu_hit_candidate_overlay_enabled") is False:
        return False
    return xueqiu_hit_outcomes_enabled(settings)


def resolve_xueqiu_hit_candidate_overlay(
    settings: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (effective_settings_copy, overlay_meta) when hit-rate triggers tuning."""
    if not xueqiu_hit_candidate_overlay_enabled(settings):
        return settings, {}

    macro_base = dict(settings.get("macro_collector") or {})
    wl_base = dict(settings.get("watchlist") or {})
    min_samples = int(
        macro_base.get(
            "xueqiu_hit_overlay_min_samples",
            (macro_base.get("xueqiu_hit_outcomes") or {}).get("min_samples", 3),
        )
    )
    low_rate = float(macro_base.get("xueqiu_hit_low_rate", 0.4))
    high_rate = float(macro_base.get("xueqiu_hit_high_rate", 0.6))
    min_misses = int(macro_base.get("xueqiu_hit_overlay_min_misses", 3))
    min_hits = int(macro_base.get("xueqiu_hit_overlay_min_hits", 3))

    stats = summarize_xueqiu_hit_outcomes()
    total = int(stats.get("total") or 0)
    if total < min_samples:
        return settings, {}

    hit_rate = stats.get("hit_rate")
    misses = int(stats.get("misses") or 0)
    hits = int(stats.get("hits") or 0)
    if not isinstance(hit_rate, (int, float)):
        return settings, {}

    if float(hit_rate) >= high_rate and hits >= min_hits:
        cfg = deepcopy(settings)
        macro = dict(cfg.get("macro_collector") or {})
        watchlist = dict(cfg.get("watchlist") or {})
        base_boost = float(macro_base.get("portfolio_hot_stock_boost", 2))
        macro["portfolio_hot_stock_boost"] = min(base_boost + 1.0, 4.0)
        watchlist["xueqiu_hot_candidates_enabled"] = True
        watchlist["eastmoney_screen_candidates_enabled"] = True
        base_max = int(wl_base.get("weekly_candidates_max", 10))
        watchlist["weekly_candidates_max"] = min(base_max + 1, 12)
        cfg["macro_collector"] = macro
        cfg["watchlist"] = watchlist
        meta = {
            "mode": "offensive",
            "hit_rate": float(hit_rate),
            "total": total,
            "hits": hits,
            "portfolio_hot_stock_boost": {
                "base": base_boost,
                "effective": macro["portfolio_hot_stock_boost"],
            },
            "weekly_candidates_max": {
                "base": base_max,
                "effective": watchlist["weekly_candidates_max"],
            },
        }
        return cfg, meta

    if misses < min_misses or float(hit_rate) >= low_rate:
        return settings, {}

    cfg = deepcopy(settings)
    macro = dict(cfg.get("macro_collector") or {})
    watchlist = dict(cfg.get("watchlist") or {})

    base_boost = float(macro_base.get("portfolio_hot_stock_boost", 2))
    macro["portfolio_hot_stock_boost"] = max(0.0, base_boost - 1.0)
    watchlist["xueqiu_hot_candidates_enabled"] = False
    watchlist["eastmoney_screen_candidates_enabled"] = False
    base_max = int(wl_base.get("weekly_candidates_max", 10))
    watchlist["weekly_candidates_max"] = max(int(wl_base.get("weekly_candidates_min", 5)), base_max - 2)

    cfg["macro_collector"] = macro
    cfg["watchlist"] = watchlist
    meta = {
        "mode": "defensive",
        "hit_rate": float(hit_rate),
        "total": total,
        "misses": misses,
        "portfolio_hot_stock_boost": {
            "base": base_boost,
            "effective": macro["portfolio_hot_stock_boost"],
        },
        "weekly_candidates_max": {
            "base": base_max,
            "effective": watchlist["weekly_candidates_max"],
        },
        "xueqiu_hot_candidates_enabled": False,
        "eastmoney_screen_candidates_enabled": False,
    }
    return cfg, meta


def apply_xueqiu_hit_candidate_overlay(settings: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Alias for harness_policy integration."""
    return resolve_xueqiu_hit_candidate_overlay(settings)

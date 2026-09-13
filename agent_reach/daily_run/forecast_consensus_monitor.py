# -*- coding: utf-8
"""Model homogeneity / consensus risk monitor (P2)."""

from __future__ import annotations

from typing import Any, Optional


def consensus_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    raw = dict((settings or {}).get("forecast_consensus") or {})
    return {
        "enabled": raw.get("enabled", True) is not False,
        "homogeneity_warn_min_symbols": max(2, int(raw.get("homogeneity_warn_min_symbols") or 3)),
    }


def _symbol_vote_bias(sym: dict[str, Any]) -> Optional[str]:
    votes = sym.get("model_votes") or sym.get("consensus") or {}
    if isinstance(votes, dict):
        bull = int(votes.get("bull") or votes.get("bullish") or votes.get("up") or 0)
        bear = int(votes.get("bear") or votes.get("bearish") or votes.get("down") or 0)
        if bull == 0 and bear >= 2:
            return "bear"
        if bear == 0 and bull >= 2:
            return "bull"
    days = sym.get("days") or {}
    dirs = [str((row or {}).get("direction") or "") for row in days.values()]
    if not dirs:
        return None
    down = sum(1 for d in dirs if d == "down")
    up = sum(1 for d in dirs if d == "up")
    if down >= max(3, len(dirs) - 1) and up == 0:
        return "bear"
    if up >= max(3, len(dirs) - 1) and down == 0:
        return "bull"
    return None


def build_homogeneity_warning(
    forecast: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    cfg = consensus_cfg(settings)
    if not cfg["enabled"]:
        return None
    symbols = forecast.get("symbols") or {}
    bearish: list[str] = []
    bullish: list[str] = []
    for code, sym in symbols.items():
        if str(sym.get("role") or "") not in ("holding", "watchlist"):
            continue
        bias = _symbol_vote_bias(sym)
        name = str(sym.get("name") or code)
        if bias == "bear":
            bearish.append(name)
        elif bias == "bull":
            bullish.append(name)
    min_n = cfg["homogeneity_warn_min_symbols"]
    if len(bearish) >= min_n:
        return {
            "kind": "homogeneous_bearish",
            "count": len(bearish),
            "symbols": bearish,
            "message": f"模型同质化警告：{len(bearish)} 只标的均为看空（{', '.join(bearish[:5])}）",
            "suggestion": "建议反向检查是否忽略利好/支撑因素",
        }
    if len(bullish) >= min_n:
        return {
            "kind": "homogeneous_bullish",
            "count": len(bullish),
            "symbols": bullish,
            "message": f"模型同质化警告：{len(bullish)} 只标的均为看多（{', '.join(bullish[:5])}）",
            "suggestion": "建议反向检查是否忽略风险/估值压力",
        }
    return None

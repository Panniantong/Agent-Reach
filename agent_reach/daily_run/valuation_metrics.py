# -*- coding: utf-8
"""Format PE / turnover for expert cards and fundamental notes."""

from __future__ import annotations

from typing import Any, Optional


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_turnover_pct(value: Any) -> Optional[float]:
    """Return turnover in percent units (e.g. 3.45 means 3.45%)."""
    raw = _optional_float(value)
    if raw is None or raw <= 0:
        return None
    if raw > 1000:
        return None
    if raw < 1:
        return raw * 100
    return raw


def format_pe_ttm(value: Any) -> Optional[str]:
    raw = _optional_float(value)
    if raw is None or raw <= 0:
        return None
    if raw > 10000:
        return None
    return f"{raw:.1f}"


def format_turnover_rate(value: Any) -> Optional[str]:
    pct = normalize_turnover_pct(value)
    if pct is None:
        return None
    return f"{pct:.2f}%"


def normalize_market_cap_yuan(value: Any) -> Optional[float]:
    raw = _optional_float(value)
    if raw is None or raw <= 0:
        return None
    if raw < 1e6:
        return raw * 1e8
    return raw


def format_market_cap(value: Any) -> Optional[str]:
    yuan = normalize_market_cap_yuan(value)
    if yuan is None:
        return None
    if yuan >= 1e12:
        return f"{yuan / 1e12:.2f}万亿"
    if yuan >= 1e8:
        return f"{yuan / 1e8:.0f}亿"
    if yuan >= 1e4:
        return f"{yuan / 1e4:.0f}万"
    return f"{yuan:.0f}"


def format_valuation_line(snapshot: dict[str, Any]) -> str:
    """One-line PE / turnover / market-cap strip for expert cards."""
    parts: list[str] = []
    pe = format_pe_ttm(snapshot.get("pe_ttm"))
    if pe:
        parts.append(f"PE(TTM) **{pe}**")
    turnover = format_turnover_rate(snapshot.get("turnover_rate"))
    if turnover:
        parts.append(f"换手率 **{turnover}**")
    cap = format_market_cap(snapshot.get("market_capital"))
    if cap:
        parts.append(f"市值 **{cap}**")
    if not parts:
        return ""
    label = snapshot.get("name") or snapshot.get("code") or "标的"
    return f"**估值快照 · {label}：** " + " · ".join(parts)

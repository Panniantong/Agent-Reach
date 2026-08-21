# -*- coding: utf-8
"""PnL harness signals → hard execution blocks at buy/sell time."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from agent_reach.daily_run.harness_policy import deep_loss_policy_default
from agent_reach.daily_run.snapshot_builder import _normalize_code

_WIN_RATE_MIN_SAMPLES = 3


def sell_loss_streak(rows: list[dict[str, Any]]) -> int:
    """Trailing consecutive losing sells (newest last in ledger replay order)."""
    streak = 0
    for row in reversed(list(rows or [])):
        pnl = row.get("realized_pnl")
        if pnl is None:
            continue
        if float(pnl) < -0.01:
            streak += 1
            continue
        if float(pnl) > 0.01:
            break
    return streak


def ledger_cost_missing(row: dict[str, Any], tolerance_cny: float) -> bool:
    cost_basis = float(row.get("cost_basis") or 0)
    return cost_basis <= tolerance_cny and int(row.get("shares") or 0) > 0


def holding_ledger_cost_unreliable(holding: dict[str, Any], tolerance_cny: float) -> bool:
    shares = int(holding.get("shares") or 0)
    if shares <= 0:
        return False
    cost = float(holding.get("cost") or 0)
    return cost * shares <= tolerance_cny


def _count_sell_wins_losses(rows: list[dict[str, Any]]) -> tuple[int, int]:
    wins = losses = 0
    for row in rows or []:
        pnl = float(row.get("realized_pnl") or 0)
        if pnl > 0.01:
            wins += 1
        elif pnl < -0.01:
            losses += 1
    return wins, losses


def _symbol_realized_sells(realized_sells: list[dict[str, Any]], code: str) -> list[dict[str, Any]]:
    norm = _normalize_code(str(code or ""))
    if not norm:
        return []
    return [
        row
        for row in realized_sells or []
        if _normalize_code(str(row.get("code") or "")) == norm
    ]


def _symbol_display_name(
    code: str,
    portfolio: Optional[dict[str, Any]] = None,
    *,
    symbol_sells: Optional[list[dict[str, Any]]] = None,
) -> str:
    norm = _normalize_code(str(code or ""))
    for row in symbol_sells or []:
        if _normalize_code(str(row.get("code") or "")) == norm:
            name = str(row.get("name") or "").strip()
            if name:
                return name
    for holding in (portfolio or {}).get("holdings") or []:
        if _normalize_code(str(holding.get("code") or "")) == norm:
            name = str(holding.get("name") or "").strip()
            if name:
                return name
    return norm or str(code or "?")


def _pnl_overview_for_portfolio(portfolio: dict[str, Any]) -> dict[str, Any]:
    from agent_reach.daily_run.realized_pnl import build_pnl_overview

    pf = {
        "holdings": [
            {
                "code": h.get("code"),
                "name": h.get("name"),
                "shares": h.get("shares"),
                "cost": h.get("cost"),
                "price": h.get("price"),
                "acquired_date": h.get("acquired_date"),
            }
            for h in portfolio.get("holdings") or []
        ]
    }
    overview = build_pnl_overview(pf, start=date(1970, 1, 1))
    return overview.to_dict()


def pnl_buy_block_reason(
    settings: dict[str, Any],
    portfolio: Optional[dict[str, Any]] = None,
    *,
    code: Optional[str] = None,
    overview: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Block new buys when symbol sell win rate or portfolio loss streak crosses thresholds."""
    win_rate_min = deep_loss_policy_default(settings, "win_rate_min")
    loss_streak_max = int(deep_loss_policy_default(settings, "loss_streak_max"))
    if win_rate_min <= 0 and loss_streak_max <= 0:
        return None

    data = overview or _pnl_overview_for_portfolio(portfolio or {})
    symbol_code = _normalize_code(str(code or ""))
    realized_sells = data.get("realized_sells") or []

    if win_rate_min > 0 and symbol_code:
        symbol_sells = _symbol_realized_sells(realized_sells, symbol_code)
        wins, losses = _count_sell_wins_losses(symbol_sells)
        total_sells = wins + losses
        if total_sells >= _WIN_RATE_MIN_SAMPLES:
            win_rate = wins / total_sells
            if win_rate < win_rate_min:
                name = _symbol_display_name(symbol_code, portfolio, symbol_sells=symbol_sells)
                return (
                    f"{name}({symbol_code}) 卖出胜率偏低（{wins}盈/{losses}亏 "
                    f"< {win_rate_min:.0%}），暂缓新开仓"
                )

    if loss_streak_max > 0:
        streak = sell_loss_streak(realized_sells)
        if streak >= loss_streak_max:
            return f"连亏警戒：连续{streak}笔卖出亏损，暂缓加仓"

    return None


def pnl_symbol_ledger_block_reason(
    settings: dict[str, Any],
    code: str,
    portfolio: Optional[dict[str, Any]] = None,
    *,
    overview: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Block buy/sell for symbols with unreliable ledger cost basis."""
    tolerance = deep_loss_policy_default(settings, "ledger_cost_tolerance_cny")
    norm = _normalize_code(str(code or ""))
    if not norm:
        return None

    pf = portfolio or {}
    for h in pf.get("holdings") or []:
        if _normalize_code(str(h.get("code", ""))) != norm:
            continue
        if holding_ledger_cost_unreliable(h, tolerance):
            name = h.get("name") or norm
            return f"{name}({norm}) ledger 缺买入成本，补全后再交易"

    data = overview or _pnl_overview_for_portfolio(pf)
    for row in data.get("realized_sells") or []:
        if _normalize_code(str(row.get("code") or "")) != norm:
            continue
        if ledger_cost_missing(row, tolerance):
            name = row.get("name") or norm
            return f"{name}({norm}) ledger 缺买入成本，补全后再交易"

    return None

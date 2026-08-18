# -*- coding: utf-8
"""Shared portfolio / symbol helpers for daily-run modules."""

from __future__ import annotations

from typing import Any

from agent_reach.daily_run.snapshot_builder import _normalize_code


def copy_portfolio(portfolio: dict[str, Any]) -> dict[str, Any]:
    pf = dict(portfolio)
    pf["holdings"] = [dict(h) for h in (portfolio.get("holdings") or [])]
    pf["watchlist"] = [dict(w) for w in (portfolio.get("watchlist") or [])]
    return pf


def build_enriched_symbols(
    snapshot: dict[str, Any],
    settings: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Merge holdings + watchlist + primary code from snapshot into one map."""
    out: dict[str, dict[str, Any]] = {}
    for h in (snapshot.get("portfolio") or {}).get("holdings") or []:
        code = _normalize_code(str(h.get("code", "")))
        if code:
            out[code] = dict(h)
    for w in snapshot.get("watchlist") or []:
        code = _normalize_code(str(w.get("code", "")))
        if code:
            out[code] = {**out.get(code, {}), **dict(w)}
    code = snapshot.get("code")
    if code:
        c = _normalize_code(str(code))
        out[c] = {
            **out.get(c, {}),
            **{k: snapshot[k] for k in ("price", "name", "change_pct", "ma20", "sector", "industry") if k in snapshot},
        }

    cfg = settings
    if cfg is None:
        try:
            from agent_reach.daily_run.settings import load_settings

            cfg = load_settings()
        except Exception:
            cfg = None
    if cfg:
        from agent_reach.daily_run.sector_classifier import enrich_symbol_map_sectors

        out = enrich_symbol_map_sectors(out, cfg)
    return out


def portfolio_from_snapshot(enriched: dict[str, Any]) -> dict[str, Any]:
    """Rebuild portfolio dict from enriched snapshot (avoids extra disk read)."""
    block = enriched.get("portfolio") or {}
    return {
        "total": block.get("total"),
        "cash": block.get("cash"),
        "cash_ratio": block.get("cash_ratio"),
        "holdings": [dict(h) for h in (block.get("holdings") or [])],
        "watchlist": [dict(w) for w in (enriched.get("watchlist") or [])],
    }


def sync_snapshot_portfolio(snapshot: dict[str, Any], portfolio: dict[str, Any]) -> None:
    """Apply portfolio.json fields onto snapshot blocks in-place."""
    snapshot["watchlist"] = list(portfolio.get("watchlist") or [])
    block = dict(snapshot.get("portfolio") or {})
    for key in ("holdings", "cash", "cash_ratio", "total"):
        if key in portfolio:
            block[key] = portfolio[key]
    snapshot["portfolio"] = block


def list_target_symbols(
    portfolio: dict[str, Any],
    *,
    mode: str = "all",
) -> list[str]:
    """Return ordered unique symbol codes from portfolio.

    mode:
      - all: holdings then watchlist (deduped)
      - holdings: holdings only
      - watchlist: watchlist only
    """
    codes: list[str] = []
    seen: set[str] = set()

    def _add(items: list[dict[str, Any]]) -> None:
        for row in items:
            code = _normalize_code(str(row.get("code", "")))
            if code and code not in seen:
                seen.add(code)
                codes.append(code)

    if mode in ("all", "holdings"):
        _add(list(portfolio.get("holdings") or []))
    if mode in ("all", "watchlist"):
        _add(list(portfolio.get("watchlist") or []))
    return codes


def resolve_target_symbols(
    portfolio: dict[str, Any],
    settings: dict[str, Any],
    *,
    workflow: str | None = None,
) -> list[str]:
    """Resolve which symbols to run for morning/close/intraday jobs.

    intraday_symbols_mode (when workflow=intraday):
      - all / holdings+watchlist: 持仓 + 观察池（去重）
      - holdings: 仅持仓
      - watchlist: 仅观察池
      - primary: 主标的
    close_symbols_mode (when workflow=close):
      - same values as intraday; defaults to schedule.symbols_mode when unset
    Falls back to schedule.symbols_mode when workflow-specific mode is unset.
    """
    sched = settings.get("schedule") or {}
    if workflow == "intraday":
        mode = str(
            sched.get("intraday_symbols_mode") or sched.get("symbols_mode", "primary")
        ).lower()
        # Shorthand: scan holdings + 观察池 (same as mode=all, excludes duplicate codes)
        if mode in ("holdings+watchlist", "holdings_watchlist"):
            mode = "all"
    elif workflow == "close":
        mode = str(
            sched.get("close_symbols_mode") or sched.get("symbols_mode", "primary")
        ).lower()
        if mode in ("holdings+watchlist", "holdings_watchlist"):
            mode = "all"
    else:
        mode = str(sched.get("symbols_mode", "primary")).lower()
    if mode == "primary":
        code = portfolio.get("primary_code")
        if not code and portfolio.get("holdings"):
            code = portfolio["holdings"][0]["code"]
        if code:
            return [_normalize_code(str(code))]
        return ["MARKET"]
    return list_target_symbols(portfolio, mode=mode)


def symbol_display_name(portfolio: dict[str, Any], code: str) -> str:
    """Best-effort name lookup from portfolio rows."""
    norm = _normalize_code(code)
    for row in list(portfolio.get("holdings") or []) + list(portfolio.get("watchlist") or []):
        if _normalize_code(str(row.get("code", ""))) == norm:
            return str(row.get("name") or norm)
    return norm

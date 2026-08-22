# -*- coding: utf-8
"""Per-symbol Xueqiu discussion snippets for portfolio holdings/watchlist."""

from __future__ import annotations

from typing import Any, Optional


def _portfolio_symbol_rows(
    portfolio: dict[str, Any],
    *,
    symbol_limit: int,
) -> list[dict[str, Any]]:
    from agent_reach.daily_run.xueqiu_hot_display import normalize_xueqiu_symbol

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for role in ("holdings", "watchlist"):
        for row in portfolio.get(role) or []:
            if not isinstance(row, dict):
                continue
            code = normalize_xueqiu_symbol(str(row.get("code") or ""))
            if not code or len(code) != 6 or code in seen:
                continue
            seen.add(code)
            rows.append(
                {
                    "code": code,
                    "name": str(row.get("name") or code),
                    "role": "holding" if role == "holdings" else "watchlist",
                }
            )
            if len(rows) >= symbol_limit:
                return rows
    return rows


def fetch_portfolio_symbol_sentiment(
    portfolio: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Fetch recent Xueqiu discussion posts per portfolio symbol."""
    from agent_reach.daily_run.settings import effective_settings, load_settings
    from agent_reach.daily_run.snapshot_builder import code_to_xueqiu_symbol

    cfg = effective_settings(settings or load_settings())
    collector_cfg = cfg.get("macro_collector") or {}
    if collector_cfg.get("fetch_symbol_sentiment", True) is False:
        return []
    if not portfolio:
        return []

    symbol_limit = int(collector_cfg.get("symbol_sentiment_symbol_limit", 5))
    post_limit = int(collector_cfg.get("symbol_sentiment_post_limit", 3))
    rows = _portfolio_symbol_rows(portfolio, symbol_limit=symbol_limit)
    if not rows:
        return []

    try:
        from agent_reach.channels import xueqiu as xq_mod

        xq_mod._ensure_cookies()
        ch = xq_mod.XueqiuChannel()
    except Exception:
        return []

    out: list[dict[str, Any]] = []
    for row in rows:
        symbol = code_to_xueqiu_symbol(row["code"])
        try:
            posts = ch.search_symbol_posts(symbol, limit=post_limit)
        except Exception:
            posts = []
        if not posts:
            continue
        out.append(
            {
                **row,
                "symbol": symbol,
                "posts": posts,
                "post_count": len(posts),
            }
        )
    return out


def attach_portfolio_symbol_sentiment(
    signals: dict[str, Any],
    portfolio: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    rows = fetch_portfolio_symbol_sentiment(portfolio, settings=settings)
    if rows:
        signals["portfolio_symbol_sentiment"] = rows
    else:
        signals.pop("portfolio_symbol_sentiment", None)
    return signals

# -*- coding: utf-8
"""Xueqiu index detail API — rise/fall/flat counts when Eastmoney clist is blocked."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Optional

_XUEQIU_BREADTH_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("SH000001", "上证"),
    ("SZ399001", "深证"),
)


def fetch_xueqiu_index_breadth(
    symbol: str,
    *,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Fetch rise/fall/flat counts from Xueqiu index detail quote."""
    from agent_reach.channels import xueqiu as xq_mod

    xq_mod._ensure_cookies()
    url = (
        "https://stock.xueqiu.com/v5/stock/quote.json?"
        f"symbol={urllib.parse.quote(symbol)}&extend=detail"
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": xq_mod._UA, "Referer": xq_mod._REFERER},
    )
    with xq_mod._opener.open(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    quote = (data.get("data") or {}).get("quote") or {}
    rise = quote.get("rise_count")
    fall = quote.get("fall_count")
    flat = quote.get("flat_count")
    if rise is None or fall is None:
        raise RuntimeError(f"xueqiu {symbol} 缺少 rise/fall 字段")
    return {
        "symbol": symbol,
        "name": str(quote.get("name") or symbol),
        "rise_count": int(rise),
        "fall_count": int(fall),
        "flat_count": int(flat or 0),
        "percent": quote.get("percent"),
    }


def fetch_xueqiu_market_breadth(
    *,
    timeout: float = 15.0,
    symbols: Optional[tuple[tuple[str, str], ...]] = None,
) -> dict[str, Any]:
    """Aggregate沪+深涨跌平家数（stock.xueqiu.com extend=detail）."""
    use_symbols = symbols or _XUEQIU_BREADTH_SYMBOLS
    by_market: dict[str, dict[str, Any]] = {}
    total_rise = total_fall = total_flat = 0
    for symbol, label in use_symbols:
        row = fetch_xueqiu_index_breadth(symbol, timeout=timeout)
        by_market[label] = row
        total_rise += int(row["rise_count"])
        total_fall += int(row["fall_count"])
        total_flat += int(row["flat_count"])

    if total_rise + total_fall + total_flat <= 0:
        raise RuntimeError("xueqiu 宽度汇总为空")

    return {
        "up_count": total_rise,
        "down_count": total_fall,
        "flat_count": total_flat,
        "by_market": by_market,
        "source": "xueqiu",
    }

# -*- coding: utf-8
"""Xueqiu K-line technicals fallback when AKShare hist is unavailable."""

from __future__ import annotations

import time
from typing import Any, Optional

from agent_reach.daily_run.quote_fetch import code_to_xueqiu_symbol, normalize_code


class XueqiuTechnicalsError(RuntimeError):
    """Raised when Xueqiu K-line technicals cannot be fetched or parsed."""


def _column_index(columns: list[str], name: str) -> int:
    try:
        return columns.index(name)
    except ValueError as exc:
        raise XueqiuTechnicalsError(f"Xueqiu K-line missing column {name}") from exc


def _parse_kline_technicals(
    data: dict[str, Any],
    *,
    lookback: int = 20,
) -> dict[str, Any]:
    payload = data.get("data") or {}
    columns = list(payload.get("column") or [])
    items = list(payload.get("item") or [])
    if not columns or len(items) < 5:
        raise XueqiuTechnicalsError("Xueqiu K-line rows insufficient")

    idx_close = _column_index(columns, "close")
    idx_volume = _column_index(columns, "volume")
    idx_ma5 = _column_index(columns, "ma5") if "ma5" in columns else None
    idx_ma20 = _column_index(columns, "ma20") if "ma20" in columns else None

    closes = [float(row[idx_close]) for row in items]
    volumes = [float(row[idx_volume]) for row in items if row[idx_volume] is not None]
    latest = closes[-1]
    window = closes[-lookback:] if len(closes) >= lookback else closes
    low = min(window)
    high = max(window)
    position_20d = (latest - low) / (high - low) if high > low else 0.5

    last = items[-1]
    ma20_raw = last[idx_ma20] if idx_ma20 is not None else None
    if ma20_raw is None:
        ma20 = sum(window) / len(window)
    else:
        ma20 = float(ma20_raw)

    ma5_raw = last[idx_ma5] if idx_ma5 is not None else None
    if ma5_raw is None:
        ma5_window = closes[-5:] if len(closes) >= 5 else closes
        ma5 = sum(ma5_window) / len(ma5_window)
    else:
        ma5 = float(ma5_raw)

    vol_ratio: Optional[float] = None
    if volumes:
        vol_window = volumes[-lookback:] if len(volumes) >= lookback else volumes
        avg_vol = sum(vol_window) / len(vol_window)
        if avg_vol > 0:
            vol_ratio = volumes[-1] / avg_vol

    return {
        "ma5": round(ma5, 2),
        "ma20": round(ma20, 2),
        "position_20d": round(position_20d, 4),
        "volume_ratio": round(vol_ratio, 2) if vol_ratio is not None else None,
        "history_days": len(closes),
        "technicals_source": "xueqiu",
    }


def fetch_technicals(code: str, *, lookback: int = 20) -> dict[str, Any]:
    """Fetch MA/volume technicals via Xueqiu chart/kline (qfq, daily)."""
    from agent_reach.channels import xueqiu as xq_mod

    symbol = code_to_xueqiu_symbol(normalize_code(code))
    begin = int(time.time() * 1000)
    count = max(-(lookback + 5), -30)
    url = (
        "https://stock.xueqiu.com/v5/stock/chart/kline.json"
        f"?symbol={symbol}&begin={begin}&period=day&type=before&count={count}&indicator=kline,ma"
    )
    data = xq_mod._get_json(url)
    if data.get("error_code") not in (0, None):
        raise XueqiuTechnicalsError(str(data.get("error_description") or data.get("error_code")))
    return _parse_kline_technicals(data, lookback=lookback)

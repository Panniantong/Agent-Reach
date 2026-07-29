# -*- coding: utf-8
"""AKShare spot cache + batch quote lookup."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

_SPOT_CACHE: dict[str, Any] = {"ts": 0.0, "rows": {}, "ttl": 60}


class AKShareError(RuntimeError):
    """Raised when AKShare is unavailable or fetch fails."""


def _import_akshare():
    try:
        import akshare as ak  # type: ignore

        return ak
    except ImportError as exc:
        raise AKShareError(
            "akshare 未安装。运行：pip install akshare 或 pip install 'agent-reach[daily-run]'"
        ) from exc


def normalize_symbol(code: str) -> tuple[str, str]:
    text = code.strip().upper()
    for prefix in ("SH", "SZ", "BJ"):
        if text.startswith(prefix):
            text = text[2:]
    text = text.zfill(6)
    if text.startswith(("5", "6", "9")):
        return text, "sh"
    if text.startswith(("0", "1", "2", "3")):
        return text, "sz"
    if text.startswith(("4", "8")):
        return text, "bj"
    return text, "sh"


def _load_spot_rows(*, ttl: int = 60) -> dict[str, dict[str, Any]]:
    now = time.time()
    if _SPOT_CACHE["rows"] and now - float(_SPOT_CACHE["ts"]) < ttl:
        return _SPOT_CACHE["rows"]

    ak = _import_akshare()
    df = ak.stock_zh_a_spot_em()
    rows: dict[str, dict[str, Any]] = {}
    for _, item in df.iterrows():
        symbol = str(item.get("代码", "")).zfill(6)
        rows[symbol] = item

    _SPOT_CACHE["ts"] = now
    _SPOT_CACHE["rows"] = rows
    _SPOT_CACHE["ttl"] = ttl
    return rows


def fetch_quotes_batch(codes: list[str], *, ttl: int = 60) -> dict[str, dict[str, Any]]:
    """Fetch multiple A-share quotes in one spot-table pass."""
    rows = _load_spot_rows(ttl=ttl)
    out: dict[str, dict[str, Any]] = {}
    for code in codes:
        symbol, _ = normalize_symbol(code)
        item = rows.get(symbol)
        if item is None:
            continue
        price = float(item["最新价"])
        industry = None
        for col in item.index:
            label = str(col)
            if "行业" in label or label in ("板块", "所属板块"):
                val = item.get(col)
                if val is not None and str(val).strip():
                    industry = str(val).strip()
                    break
        row_out: dict[str, Any] = {
            "code": symbol,
            "name": str(item.get("名称", symbol)),
            "price": price,
            "change_pct": float(item.get("涨跌幅", 0)),
            "volume_ratio": _optional_float(item.get("量比")),
            "turnover": float(item.get("成交额", 0) or 0),
            "source": "akshare_spot_em",
        }
        if industry:
            row_out["industry"] = industry
            row_out["sector"] = industry
        out[symbol] = row_out
    return out


def fetch_quote(code: str, *, ttl: int = 60) -> dict[str, Any]:
    symbol, _ = normalize_symbol(code)
    batch = fetch_quotes_batch([symbol], ttl=ttl)
    if symbol not in batch:
        raise AKShareError(f"未找到股票代码 {symbol}")
    return batch[symbol]


def fetch_technicals(code: str, *, lookback: int = 20) -> dict[str, Any]:
    ak = _import_akshare()
    symbol, _market = normalize_symbol(code)
    hist = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq")
    if hist is None or len(hist) < 5:
        raise AKShareError(f"历史 K 线不足：{symbol}")

    closes = hist["收盘"].astype(float).tolist()
    volumes = hist["成交量"].astype(float).tolist()
    latest = closes[-1]
    window = closes[-lookback:] if len(closes) >= lookback else closes
    ma20 = sum(window) / len(window)
    low = min(window)
    high = max(window)
    position_20d = (latest - low) / (high - low) if high > low else 0.5

    avg_vol = sum(volumes[-lookback:]) / min(len(volumes), lookback)
    vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else None

    ma5 = sum(closes[-5:]) / min(len(closes), 5)

    return {
        "ma5": round(ma5, 2),
        "ma20": round(ma20, 2),
        "position_20d": round(position_20d, 4),
        "volume_ratio": round(vol_ratio, 2) if vol_ratio is not None else None,
        "history_days": len(closes),
    }


def enrich_snapshot(snapshot: dict[str, Any], code: str) -> dict[str, Any]:
    quote = fetch_quote(code)
    technicals = fetch_technicals(code)

    merged = dict(snapshot)
    merged.setdefault("as_of", datetime.now(timezone.utc).isoformat())
    merged["code"] = quote["code"]
    merged["name"] = quote.get("name") or merged.get("name")
    merged["price"] = quote["price"]
    merged["reference_price"] = merged.get("reference_price", quote["price"])
    merged["change_pct"] = quote["change_pct"]
    merged.update(technicals)
    if quote.get("volume_ratio") is not None and merged.get("volume_ratio") is None:
        merged["volume_ratio"] = quote["volume_ratio"]

    sources = dict(merged.get("sources") or {})
    sources["quote"] = {
        "summary": f"AKShare {quote['name']} {quote['price']} ({quote['change_pct']:+.2f}%)",
        "backend": "akshare",
    }
    merged["sources"] = sources
    merged["structured_review_complete"] = True
    return merged


def _optional_float(value: Any) -> Optional[float]:
    if value is None or value == "" or value == "-":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

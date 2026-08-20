# -*- coding: utf-8
"""Eastmoney push2 / datacenter helpers for market-wide review."""

from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from typing import Any, Optional

from agent_reach.daily_run.retry_utils import retry_with_backoff

_EASTMONEY_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_EASTMONEY_REFERER = "https://quote.eastmoney.com/center/gridlist.html"
_DC_REFERER = "https://data.eastmoney.com/"
_ALL_STOCK_FS = ",".join(["m:0+t:6", "m:0+t:80", "m:1+t:2", "m:1+t:23"])
_ALL_STOCK_FIELDS = "f2,f3,f4,f5,f6,f8,f12,f14,f20,f21,f100,f102"


def fetch_json(url: str, *, timeout: float = 15.0, referer: str = _EASTMONEY_REFERER) -> Any:
    ctx = ssl.create_default_context()

    def _once() -> Any:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _EASTMONEY_UA,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": referer,
            },
        )
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))

    return retry_with_backoff(_once, max_retries=2, label="eastmoney_json")


def fetch_indices(*, timeout: float = 15.0) -> dict[str, dict[str, Any]]:
    secids = ["1.000001", "0.399001", "0.399006", "1.000688", "1.000300"]
    url = (
        "https://push2.eastmoney.com/api/qt/ulist.np/get"
        f"?fltt=2&fields=f2,f3,f4,f5,f6,f7,f12,f14,f15,f16,f17,f18"
        f"&secids={','.join(secids)}"
    )
    data = fetch_json(url, timeout=timeout)
    names = {
        "000001": "上证指数",
        "399001": "深证成指",
        "399006": "创业板指",
        "000688": "科创50",
        "000300": "沪深300",
    }
    codes = {
        "000001": "sh000001",
        "399001": "sz399001",
        "399006": "sz399006",
        "000688": "sh000688",
        "000300": "sh000300",
    }
    out: dict[str, dict[str, Any]] = {}
    for item in (data.get("data") or {}).get("diff") or []:
        key = codes.get(str(item.get("f12")), str(item.get("f12")))
        out[key] = {
            "name": names.get(str(item.get("f12")), item.get("f14")),
            "price": item.get("f2"),
            "change_pct": item.get("f3"),
            "change_amount": item.get("f4"),
            "volume": item.get("f5"),
            "amount": item.get("f6"),
            "amplitude": item.get("f7"),
            "high": item.get("f15"),
            "low": item.get("f16"),
            "open": item.get("f17"),
            "prev_close": item.get("f18"),
        }
    return out


def _parse_stock_rows(data: Any) -> list[dict[str, Any]]:
    stocks: list[dict[str, Any]] = []
    for item in (data.get("data") or {}).get("diff") or []:
        stocks.append(
            {
                "code": item.get("f12"),
                "name": item.get("f14"),
                "price": item.get("f2"),
                "change_pct": item.get("f3"),
                "volume": item.get("f5"),
                "amount": item.get("f6"),
                "turnover": item.get("f8"),
                "total_cap": item.get("f20"),
                "circ_cap": item.get("f21"),
                "industry": item.get("f100") or "",
                "concept": item.get("f102") or "",
                "source": "eastmoney",
            }
        )
    return stocks


def fetch_all_stocks(
    *,
    timeout: float = 20.0,
    page_size: int = 500,
    max_pages: int = 20,
) -> list[dict[str, Any]]:
    """Paginated Eastmoney clist — lighter pages than single pz=6000 burst."""
    stocks: list[dict[str, Any]] = []
    total_expected: Optional[int] = None
    for page in range(1, max_pages + 1):
        url = (
            "https://push2.eastmoney.com/api/qt/clist/get"
            f"?pn={page}&pz={page_size}&po=1&np=1&fltt=2&invt=2&fid=f3&fs={_ALL_STOCK_FS}"
            f"&fields={_ALL_STOCK_FIELDS}"
        )
        data = fetch_json(url, timeout=timeout)
        batch = _parse_stock_rows(data)
        if not batch:
            break
        stocks.extend(batch)
        if total_expected is None:
            try:
                total_expected = int((data.get("data") or {}).get("total") or 0)
            except (TypeError, ValueError):
                total_expected = 0
        if total_expected and len(stocks) >= total_expected:
            break
        if len(batch) < page_size:
            break
    if not stocks:
        raise RuntimeError("eastmoney clist 返回空列表")
    return stocks


def fetch_all_stocks_resilient(
    *,
    timeout: float = 20.0,
    akshare_ttl: int = 60,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    """Eastmoney paginated clist → akshare spot fallback."""
    warnings: list[str] = []
    try:
        stocks = fetch_all_stocks(timeout=timeout)
        return stocks, "eastmoney", warnings
    except Exception as exc:
        warnings.append(f"eastmoney clist: {exc}")

    try:
        from agent_reach.daily_run.akshare_adapter import fetch_all_a_spot_stocks

        stocks = fetch_all_a_spot_stocks(ttl=akshare_ttl)
        warnings.append("市场宽度改用 akshare spot 回退")
        return stocks, "akshare", warnings
    except Exception as exc:
        warnings.append(f"akshare spot: {exc}")

    return [], "none", warnings


def fetch_north_flow(*, timeout: float = 15.0) -> dict[str, Any]:
    url = (
        "https://push2.eastmoney.com/api/qt/kamt.kline/get"
        "?fields1=f1,f2,f3,f4&fields2=f51,f52,f53&klt=101&lmt=10"
    )
    data = fetch_json(url, timeout=timeout)
    result: dict[str, Any] = {"net_yi": 0.0, "direction": "flat", "recent": []}
    lines = (data.get("data") or {}).get("klines") or []
    for line in lines:
        parts = str(line).split(",")
        result["recent"].append(
            {
                "date": parts[0] if parts else "",
                "value": float(parts[1]) if len(parts) > 1 else 0.0,
                "balance": float(parts[2]) if len(parts) > 2 else 0.0,
            }
        )
    if result["recent"]:
        last = result["recent"][-1]
        result["net_yi"] = float(last.get("value") or 0)
        val = result["net_yi"]
        result["direction"] = "inflow" if val > 0 else "outflow" if val < 0 else "flat"
    return result


def fetch_north_flow_resilient(*, timeout: float = 15.0) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    try:
        return fetch_north_flow(timeout=timeout), warnings
    except Exception as exc:
        warnings.append(f"eastmoney 北向: {exc}")

    try:
        from agent_reach.daily_run.macro_collector import _fetch_northbound_flow

        net = _fetch_northbound_flow()
        if net is not None:
            val = float(net)
            return (
                {
                    "net_yi": val,
                    "direction": "inflow" if val > 0 else "outflow" if val < 0 else "flat",
                    "recent": [],
                    "source": "akshare_macro",
                },
                [*warnings, "北向改用 akshare/macro 回退"],
            )
    except Exception as exc:
        warnings.append(f"akshare 北向: {exc}")

    return {"net_yi": 0.0, "direction": "flat", "recent": []}, warnings


def _safe_list(fetch_fn, *, timeout: float, label: str) -> tuple[list[Any], list[str]]:
    try:
        return fetch_fn(timeout=timeout), []
    except Exception as exc:
        return [], [f"{label}: {exc}"]


def fetch_industry_boards(*, timeout: float = 15.0) -> list[dict[str, Any]]:
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=50&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t:2"
        "&fields=f2,f3,f4,f12,f14,f104,f105,f128,f140"
    )
    return _parse_board_rows(fetch_json(url, timeout=timeout))


def fetch_concept_boards(*, timeout: float = 15.0) -> list[dict[str, Any]]:
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=50&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t:3"
        "&fields=f2,f3,f4,f12,f14,f104,f105,f128,f140"
    )
    return _parse_board_rows(fetch_json(url, timeout=timeout))


def fetch_sector_fund_flow(*, timeout: float = 15.0) -> list[dict[str, Any]]:
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=50&po=1&np=1&fltt=2&invt=2&fid=f62&fs=m:90+t:2"
        "&fields=f2,f3,f12,f14,f62,f184,f66,f69,f72,f75,f204,f205"
    )
    data = fetch_json(url, timeout=timeout)
    flows: list[dict[str, Any]] = []
    for item in (data.get("data") or {}).get("diff") or []:
        flows.append(
            {
                "code": item.get("f12"),
                "name": item.get("f14"),
                "change_pct": item.get("f3"),
                "main_net": item.get("f62"),
                "main_net_pct": item.get("f184"),
                "super_large_net": item.get("f66"),
                "large_net": item.get("f69"),
                "medium_net": item.get("f72"),
                "small_net": item.get("f75"),
            }
        )
    return flows


def fetch_fund_flow_rank(*, timeout: float = 15.0) -> list[dict[str, Any]]:
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz=30&po=1&np=1&fltt=2&invt=2&fid=f62&fs={_ALL_STOCK_FS}"
        "&fields=f2,f3,f12,f14,f62,f184"
    )
    data = fetch_json(url, timeout=timeout)
    stocks: list[dict[str, Any]] = []
    for item in (data.get("data") or {}).get("diff") or []:
        stocks.append(
            {
                "code": item.get("f12"),
                "name": item.get("f14"),
                "change_pct": item.get("f3"),
                "price": item.get("f2"),
                "main_net": item.get("f62"),
                "main_net_pct": item.get("f184"),
            }
        )
    return stocks


def fetch_lhb(date_str: str, *, timeout: float = 15.0) -> list[dict[str, Any]]:
    dc = date_str.replace("-", "")
    filt = f"(TRADE_DATE='{dc}')"
    params = urllib.parse.urlencode(
        {
            "reportName": "RPT_DAILY_BILLRANKING",
            "columns": "ALL",
            "pageNumber": "1",
            "pageSize": "30",
            "sortColumns": "NET_BUY_AMT",
            "sortTypes": "-1",
            "filter": filt,
        }
    )
    url = f"https://datacenter.eastmoney.com/securities/api/data/v1/get?{params}"
    try:
        data = fetch_json(url, timeout=timeout, referer=_DC_REFERER)
    except Exception:
        return []
    stocks: list[dict[str, Any]] = []
    for item in (data.get("result") or {}).get("data") or []:
        stocks.append(
            {
                "code": item.get("SECURITY_CODE"),
                "name": item.get("SECURITY_NAME_ABBR"),
                "change_pct": item.get("CHANGE_RATE"),
                "close": item.get("CLOSE_PRICE"),
                "net_buy": (item.get("NET_BUY_AMT") or 0) / 1e8 if item.get("NET_BUY_AMT") else None,
                "buy_amt": (item.get("BUY_AMT") or 0) / 1e8 if item.get("BUY_AMT") else None,
                "sell_amt": (item.get("SELL_AMT") or 0) / 1e8 if item.get("SELL_AMT") else None,
                "turnover": item.get("TURNOVERRATE"),
                "reason": item.get("EXPLANATION") or "",
                "net_buy_ratio": item.get("NET_BUY_RATE"),
            }
        )
    return stocks


def _parse_board_rows(data: Any) -> list[dict[str, Any]]:
    boards: list[dict[str, Any]] = []
    for item in (data.get("data") or {}).get("diff") or []:
        boards.append(
            {
                "code": item.get("f12"),
                "name": item.get("f14"),
                "change_pct": item.get("f3"),
                "price": item.get("f2"),
                "up_count": item.get("f104"),
                "down_count": item.get("f105"),
                "leader": item.get("f128"),
                "leader_chg": item.get("f140"),
            }
        )
    return boards

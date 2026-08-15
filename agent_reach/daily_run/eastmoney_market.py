# -*- coding: utf-8
"""Eastmoney push2 / datacenter helpers for market-wide review."""

from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from typing import Any, Optional

_EASTMONEY_UA = "Mozilla/5.0 (compatible; AgentReach/1.0)"
_EASTMONEY_REFERER = "https://quote.eastmoney.com/"
_DC_REFERER = "https://data.eastmoney.com/"


def fetch_json(url: str, *, timeout: float = 15.0, referer: str = _EASTMONEY_REFERER) -> Any:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _EASTMONEY_UA,
            "Accept": "application/json, text/plain, */*",
            "Referer": referer,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


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


def fetch_all_stocks(*, timeout: float = 20.0) -> list[dict[str, Any]]:
    fs = ",".join(["m:0+t:6", "m:0+t:80", "m:1+t:2", "m:1+t:23"])
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz=6000&po=1&np=1&fltt=2&invt=2&fid=f3&fs={fs}"
        "&fields=f2,f3,f4,f5,f6,f8,f12,f14,f20,f21,f100,f102"
    )
    data = fetch_json(url, timeout=timeout)
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
            }
        )
    return stocks


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
    fs = ",".join(["m:0+t:6", "m:0+t:80", "m:1+t:2", "m:1+t:23"])
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz=30&po=1&np=1&fltt=2&invt=2&fid=f62&fs={fs}"
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

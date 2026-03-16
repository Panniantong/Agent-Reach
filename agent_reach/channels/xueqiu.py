# -*- coding: utf-8 -*-
"""Xueqiu (雪球) — stock quotes, search, trending posts & hot stocks."""

import http.cookiejar
import json
import re
import urllib.request
from typing import Any

from .base import Channel

_UA = "agent-reach/1.0"
_TIMEOUT = 10
_XUEQIU_HOME = "https://xueqiu.com"

# --------------- cookie-aware HTTP helpers --------------- #

_cookie_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(_cookie_jar),
)
_cookies_initialized = False


def _ensure_cookies() -> None:
    """Visit xueqiu.com homepage once to obtain session cookies."""
    global _cookies_initialized
    if _cookies_initialized:
        return
    req = urllib.request.Request(_XUEQIU_HOME, headers={"User-Agent": _UA})
    _opener.open(req, timeout=_TIMEOUT)
    _cookies_initialized = True


def _get_json(url: str) -> Any:
    """Fetch *url* with Xueqiu session cookies and return parsed JSON."""
    _ensure_cookies()
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with _opener.open(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = re.sub(r"<[^>]+>", "", text)
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">")):
        text = text.replace(entity, char)
    return text.strip()


class XueqiuChannel(Channel):
    name = "xueqiu"
    description = "雪球股票行情与社区动态"
    backends = ["Xueqiu API (public)"]
    tier = 0

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "xueqiu.com" in d

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        try:
            data = _get_json("https://stock.xueqiu.com/v5/stock/batch/quote.json?symbol=SH000001")
            items = (data.get("data") or {}).get("items") or []
            if items:
                return "ok", "公开 API 可用（行情、搜索、热帖、热股）"
            return "warn", "API 响应异常（返回数据为空）"
        except Exception as e:
            return "warn", f"Xueqiu API 连接失败（可能需要代理）：{e}"

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    def get_stock_quote(self, symbol: str) -> dict:
        """获取实时股票行情。

        Args:
            symbol: 股票代码，如 SH600519（沪）、SZ000858（深）、AAPL（美）、00700（港）

        Returns a dict with keys:
          symbol, name, current, percent, chg, high, low, open, last_close,
          volume, amount, market_capital, turnover_rate, pe_ttm, timestamp
        """
        data = _get_json(f"https://stock.xueqiu.com/v5/stock/batch/quote.json?symbol={symbol}")
        items = (data.get("data") or {}).get("items") or []
        q = (items[0].get("quote") or {}) if items else {}
        return {
            "symbol": q.get("symbol", symbol),
            "name": q.get("name", ""),
            "current": q.get("current"),
            "percent": q.get("percent"),
            "chg": q.get("chg"),
            "high": q.get("high"),
            "low": q.get("low"),
            "open": q.get("open"),
            "last_close": q.get("last_close"),
            "volume": q.get("volume"),
            "amount": q.get("amount"),
            "market_capital": q.get("market_capital"),
            "turnover_rate": q.get("turnover_rate"),
            "pe_ttm": q.get("pe_ttm"),
            "timestamp": q.get("timestamp"),
        }

    def search_stock(self, query: str, limit: int = 10) -> list:
        """搜索股票。

        Args:
            query: 股票代码或中文名称，如 "茅台"、"600519"
            limit: 最多返回条数

        Returns a list of dicts with keys:
          symbol, name, exchange
        """
        data = _get_json(
            f"https://xueqiu.com/stock/search.json?code={urllib.request.quote(query)}&size={limit}"
        )
        stocks = data.get("stocks") or []
        results = []
        for s in stocks[:limit]:
            results.append(
                {
                    "symbol": s.get("code", ""),
                    "name": s.get("name", ""),
                    "exchange": s.get("exchange", ""),
                }
            )
        return results

    def get_hot_posts(self, limit: int = 20) -> list:
        """获取雪球热门帖子。

        Args:
            limit: 最多返回条数（上限 50）

        Returns a list of dicts with keys:
          id, title, text, author, likes, url
        """
        data = _get_json("https://xueqiu.com/statuses/hot/listV3.json?source=hot&page=1")
        items = (data.get("data") or {}).get("items") or []
        results = []
        for item in items[:limit]:
            original = item.get("original_status") or item
            text = _strip_html(original.get("text") or original.get("description") or "")
            user = original.get("user") or {}
            results.append(
                {
                    "id": original.get("id", 0),
                    "title": original.get("title") or "",
                    "text": text[:200],
                    "author": user.get("screen_name", ""),
                    "likes": original.get("like_count", 0),
                    "url": f"https://xueqiu.com{original['target']}"
                    if original.get("target")
                    else "",
                }
            )
        return results

    def get_hot_stocks(self, limit: int = 10, stock_type: int = 10) -> list:
        """获取热门股票排行。

        Args:
            limit:      最多返回条数（上限 50）
            stock_type: 10=人气榜（默认），12=关注榜

        Returns a list of dicts with keys:
          symbol, name, current, percent, rank
        """
        data = _get_json(
            f"https://stock.xueqiu.com/v5/stock/hot_stock/list.json?size={limit}&type={stock_type}"
        )
        items = (data.get("data") or {}).get("items") or []
        results = []
        for idx, item in enumerate(items[:limit], 1):
            results.append(
                {
                    "symbol": item.get("code") or item.get("symbol", ""),
                    "name": item.get("name", ""),
                    "current": item.get("current"),
                    "percent": item.get("percent"),
                    "rank": idx,
                }
            )
        return results

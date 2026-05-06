# -*- coding: utf-8 -*-
"""Xueqiu (雪球) — stock quotes, search, trending posts & hot stocks."""

import http.cookiejar
import json
import re
import urllib.parse
import urllib.request
from typing import Any

from .base import Channel

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_REFERER = "https://xueqiu.com/"
_TIMEOUT = 10
_XUEQIU_HOME = "https://xueqiu.com"

# --------------- cookie-aware HTTP helpers --------------- #

_cookie_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(_cookie_jar),
)
_cookies_initialized = False


def _inject_cookie_string(cookie_str: str) -> None:
    """Parse a 'name=value; name2=value2' string and inject into the cookie jar."""
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        cookie = http.cookiejar.Cookie(
            version=0,
            name=name.strip(),
            value=value.strip(),
            port=None,
            port_specified=False,
            domain=".xueqiu.com",
            domain_specified=True,
            domain_initial_dot=True,
            path="/",
            path_specified=True,
            secure=True,
            expires=None,
            discard=True,
            comment=None,
            comment_url=None,
            rest={},
        )
        _cookie_jar.set_cookie(cookie)


def _load_cookies_from_config() -> bool:
    """Try to load Xueqiu cookies from hivereach config file (xueqiu_cookie key)."""
    try:
        from ..config import Config

        cfg = Config()
        cookie_str = cfg.get("xueqiu_cookie")
        if not cookie_str:
            return False
        _inject_cookie_string(cookie_str)
        return True
    except Exception:
        return False


def _load_cookies_from_browser() -> bool:
    """Try to silently load Xueqiu cookies from the local Chrome browser.

    Only succeeds when browser_cookie3 is installed AND the user is logged in
    (xq_a_token present).  Failures are silently ignored so that agents without
    a local browser keep working.
    """
    try:
        try:
            import rookiepy
            cookies = rookiepy.chrome([".xueqiu.com"])
            if not any(c.get("name") == "xq_a_token" for c in cookies):
                return False
            for c in cookies:
                _cookie_jar.set(c["name"], c["value"], domain=c.get("domain", ".xueqiu.com"))
            return True
        except ImportError:
            import browser_cookie3
            cookies = list(browser_cookie3.chrome(domain_name=".xueqiu.com"))
            if not any(c.name == "xq_a_token" for c in cookies):
                return False
            for c in cookies:
                _cookie_jar.set_cookie(c)
            return True
    except Exception:
        return False


def _ensure_cookies() -> None:
    """Populate session cookies using the best available source.

    Priority order:
    1. Saved cookie string in ~/.hivereach/config.yaml  (set by configure --from-browser)
    2. Live Chrome browser cookies via rookiepy/browser_cookie3 (if installed + logged in)
    3. Homepage visit fallback                             (only yields anti-DDoS acw_tc,
                                                           not enough for stock APIs)
    """
    global _cookies_initialized
    if _cookies_initialized:
        return
    if _load_cookies_from_config():
        _cookies_initialized = True
        return
    if _load_cookies_from_browser():
        _cookies_initialized = True
        return
    # Fallback: visit homepage to pick up acw_tc anti-DDoS cookie.
    # This is not sufficient for authenticated APIs but avoids hard failures
    # on public endpoints that only need the session cookie.
    req = urllib.request.Request(_XUEQIU_HOME, headers={"User-Agent": _UA})
    _opener.open(req, timeout=_TIMEOUT)
    _cookies_initialized = True


def _get_json(url: str) -> Any:
    """Fetch *url* with Xueqiu session cookies and return parsed JSON."""
    _ensure_cookies()
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Referer": _REFERER}
    )
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
    backends = ["Xueqiu API (需要登录 Cookie)"]
    tier = 1

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        d = urllib.parse.urlparse(url).netloc.lower()
        return "xueqiu.com" in d

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        try:
            data = _get_json(
                "https://stock.xueqiu.com/v5/stock/batch/quote.json?symbol=SH000001"
            )
            items = (data.get("data") or {}).get("items") or []
            if items:
                return "ok", "公开 API 可用（行情、搜索、热帖、热股）"
            return "warn", "API 响应异常（返回数据为空）"
        except Exception as e:
            return "warn", (
                f"Xueqiu API 连接失败：{e}。"
                "请先登录雪球后运行：hivereach configure --from-browser chrome"
            )

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
        data = _get_json(
            f"https://stock.xueqiu.com/v5/stock/batch/quote.json?symbol={symbol}"
        )
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
            f"https://xueqiu.com/stock/search.json"
            f"?code={urllib.parse.quote(query)}&size={limit}"
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

        Uses the v4 public timeline endpoint which returns posts in a `list`
        array.  Each item carries a JSON-encoded `data` field containing the
        actual post payload (title, description, user, like_count, target).

        Args:
            limit: 最多返回条数（上限 50）

        Returns a list of dicts with keys:
          id, title, text, author, likes, url
        """
        data = _get_json(
            "https://xueqiu.com/v4/statuses/public_timeline_by_category.json"
            "?since_id=-1&max_id=-1&count=20&category=-1"
        )
        items = data.get("list") or []
        results = []
        for item in items[:limit]:
            # Each item.data is a JSON string containing the real post payload
            try:
                post = (
                    json.loads(item["data"])
                    if isinstance(item.get("data"), str)
                    else {}
                )
            except (json.JSONDecodeError, KeyError):
                post = {}
            user = post.get("user") or {}
            text = _strip_html(
                post.get("text") or post.get("description") or ""
            )
            target = post.get("target", "")
            results.append(
                {
                    "id": post.get("id", 0),
                    "title": post.get("title") or "",
                    "text": text[:200],
                    "author": user.get("screen_name", ""),
                    "likes": post.get("like_count", 0),
                    "url": f"https://xueqiu.com{target}" if target else "",
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
            f"https://stock.xueqiu.com/v5/stock/hot_stock/list.json"
            f"?size={limit}&type={stock_type}"
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

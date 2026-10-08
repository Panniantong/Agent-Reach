# -*- coding: utf-8 -*-
"""Xueqiu (雪球) — stock quotes, search, trending posts & hot stocks."""

import http.cookiejar
import json
import re
import urllib.parse
import urllib.request
from typing import Any
from urllib.error import HTTPError, URLError

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
_cookie_source: str | None = None


class XueqiuSessionRejected(RuntimeError):
    """A structured 400016 response, not proof that a saved cookie expired."""


def _session_rejected(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("error_code") in (400016, "400016")


def _http_session_rejected(error: HTTPError) -> bool:
    """Inspect only a small 400 body, without exposing server-provided text."""
    if error.code != 400:
        return False
    try:
        body = error.read(4097)
        if len(body) > 4096:
            return False
        return _session_rejected(json.loads(body.decode("utf-8")))
    except (OSError, ValueError, TypeError):
        return False


def _session_recovery_message() -> str:
    message = "雪球拒绝当前会话（error_code=400016），不能仅据此断定 Cookie 已过期。"
    if _cookie_source == "file":
        return message + (
            "当前使用 config.yaml 中保存的 xueqiu_cookie，可能已过期或不被接受。"
            "如决定停止使用它，请运行：agent-reach configure --unset xueqiu-cookie；"
            "该命令不清除浏览器 Cookie 或环境变量，请在新进程中重试。"
        )
    if _cookie_source == "env":
        return message + (
            "当前使用环境变量 XUEQIU_COOKIE，可能已过期或不被接受；"
            "请在自己控制的运行环境中移除或更新该变量，并在新进程中重试。"
        )
    if _cookie_source == "anonymous":
        return message + "当前匿名会话未被接受，请检查匿名会话获取路径及网络；不要据此删除保存的凭据。"
    return message + "当前凭据来源未确认，请先检查调用环境；不要自动删除或导入凭据。"


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


def _load_cookies_from_config(config=None) -> bool:
    """Try to load Xueqiu cookies from agent-reach config file (xueqiu_cookie key)."""
    global _cookie_source
    try:
        from ..config import Config

        cfg = config if config is not None else Config(read_only=True)
        cookie_str = cfg.get("xueqiu_cookie")
        if not cookie_str:
            return False
        _inject_cookie_string(cookie_str)
        _cookie_source = "file" if "xueqiu_cookie" in cfg.data else "env"
        return True
    except Exception:
        return False


def _ensure_cookies(config=None) -> None:
    """Populate session cookies without touching browser credential stores.

    Priority order:
    1. Saved cookie string in ~/.agent-reach/config.yaml  (set by configure --from-browser)
    2. Homepage visit fallback (only yields public session cookies and may not
       be sufficient when Xueqiu requires a logged-in session)
    """
    global _cookies_initialized, _cookie_source
    if _cookies_initialized:
        return
    _cookie_source = None
    if _load_cookies_from_config(config):
        _cookies_initialized = True
        return
    # Fallback: visit homepage to pick up acw_tc anti-DDoS cookie.
    # This is not sufficient for authenticated APIs but avoids hard failures
    # on public endpoints that only need the session cookie.
    req = urllib.request.Request(_XUEQIU_HOME, headers={"User-Agent": _UA})
    _cookie_source = "anonymous"
    _opener.open(req, timeout=_TIMEOUT)
    _cookies_initialized = True


def _get_json(url: str, config=None) -> Any:
    """Fetch *url* with Xueqiu session cookies and return parsed JSON."""
    _ensure_cookies(config)
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Referer": _REFERER}
    )
    # Leave HTTP errors and their streams untouched for data callers.
    # Only the health check owns bounded inspection of a rejected response.
    with _opener.open(req, timeout=_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if _session_rejected(data):
        raise XueqiuSessionRejected("Xueqiu error_code=400016")
    return data


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
        from agent_reach.utils.url import host_matches

        return host_matches(url, "xueqiu.com")

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        self.active_backend = None
        try:
            data = _get_json(
                "https://stock.xueqiu.com/v5/stock/quote.json"
                "?symbol=SH601138&extend=detail",
                config,
            )
            quote = (data.get("data") or {}).get("quote") or {}
            if quote:
                self.active_backend = self.backends[0]
                return "ok", "公开 API 可用（行情、搜索、热帖、热股）"
            return "warn", "API 响应异常（返回数据为空）"
        except XueqiuSessionRejected:
            return "warn", _session_recovery_message()
        except HTTPError as e:
            try:
                if _http_session_rejected(e):
                    return "warn", _session_recovery_message()
                return "warn", f"Xueqiu API 请求失败（HTTP {e.code}）；没有足够证据判断 Cookie 过期，请检查请求和服务状态。"
            finally:
                e.close()
        except (URLError, TimeoutError, OSError):
            return "warn", "Xueqiu API 连接失败；请检查网络、代理或服务状态，不能据此判断 Cookie 过期。"
        except (ValueError, TypeError, AttributeError):
            return "warn", "Xueqiu API 响应格式异常；不能据此判断 Cookie 过期。"
        except Exception:
            return "warn", "Xueqiu API 检查失败；没有足够证据判断 Cookie 过期，doctor 不会修改凭据或读取浏览器 Cookie。"

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    def get_stock_quote(self, symbol: str) -> dict:
        """获取实时股票行情。

        Args:
            symbol: 股票代码，如 SH600519（沪）、SZ000858（深）、AAPL（美）、00700（港）

        Returns a dict with keys:
          symbol, name, current, percent, chg, high, low, open, last_close,
          volume, amount, market_capital, turnover_rate, pe_ttm, pe_forecast,
          pb, eps, timestamp
        """
        encoded_symbol = urllib.parse.quote(symbol, safe="")
        data = _get_json(
            "https://stock.xueqiu.com/v5/stock/quote.json"
            f"?symbol={encoded_symbol}&extend=detail"
        )
        q = (data.get("data") or {}).get("quote") or {}
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
            "pe_forecast": q.get("pe_forecast"),
            "pb": q.get("pb"),
            "eps": q.get("eps"),
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
        if limit < 0:
            raise ValueError("limit must be non-negative")
        limit = min(limit, 50)
        if limit == 0:
            return []
        data = _get_json(
            "https://xueqiu.com/v4/statuses/public_timeline_by_category.json"
            f"?since_id=-1&max_id=-1&count={limit}&category=-1"
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

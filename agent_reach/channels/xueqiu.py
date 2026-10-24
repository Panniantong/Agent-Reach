# -*- coding: utf-8 -*-
"""Xueqiu (雪球) — stock quotes, search, trending posts & hot stocks."""

import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from agent_reach.runtime.result import (
    BAD_INPUT,
    NEED_LOGIN,
    NOT_FOUND,
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
)
from agent_reach.runtime.run import http_request

from .base import Action, Channel, Param

_XQ_LOGIN_HINT = (
    "Xueqiu community data needs a browser session. Run `agent-reach login xueqiu`, "
    "let the user open xueqiu.com in the Agent Reach browser, then run "
    "`agent-reach login xueqiu --sync`. The session expires within hours; repeat these steps when it does."
)

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


def _load_cookies_from_config(config=None) -> bool:
    """Try to load Xueqiu cookies from agent-reach config file (xueqiu_cookie key)."""
    try:
        from ..config import Config

        cfg = config if config is not None else Config(read_only=True)
        cookie_str = cfg.get("xueqiu_cookie")
        if not cookie_str:
            return False
        _inject_cookie_string(cookie_str)
        return True
    except Exception:
        return False


def _ensure_cookies(config=None) -> None:
    """Populate session cookies without touching browser credential stores.

    Priority order:
    1. Saved cookie string in ~/.agent-reach/config.yaml  (set by `agent-reach login xueqiu --sync`)
    2. Homepage visit fallback (only yields public session cookies and may not
       be sufficient when Xueqiu requires a logged-in session)
    """
    global _cookies_initialized
    if _cookies_initialized:
        return
    if _load_cookies_from_config(config):
        _cookies_initialized = True
        return
    # Fallback: visit homepage to pick up acw_tc anti-DDoS cookie.
    # This is not sufficient for authenticated APIs but avoids hard failures
    # on public endpoints that only need the session cookie.
    req = urllib.request.Request(_XUEQIU_HOME, headers={"User-Agent": _UA})
    _opener.open(req, timeout=_TIMEOUT)
    _cookies_initialized = True


def _get_json(url: str, config=None) -> Any:
    """Fetch *url* with Xueqiu session cookies and return parsed JSON."""
    _ensure_cookies(config)
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


def _tencent_code(symbol: str) -> str:
    """SH600519 / 600519 / HK00700 / 00700 / AAPL → Tencent quote code."""
    s = str(symbol).strip().upper()
    if re.fullmatch(r"(SH|SZ|BJ)\d{6}", s):
        return s.lower()
    if re.fullmatch(r"\d{6}", s):
        prefix = "sh" if s[0] in "69" else ("bj" if s[0] in "48" else "sz")
        return prefix + s
    if re.fullmatch(r"HK\d{1,5}", s):
        return "hk" + s[2:].zfill(5)
    if re.fullmatch(r"\d{1,5}", s):
        return "hk" + s.zfill(5)
    if re.fullmatch(r"[A-Z][A-Z.\-]{0,9}", s):
        return "us" + s
    raise ReachError(BAD_INPUT, "symbol must look like SH600519, 600519, 00700 or AAPL")


def _xueqiu_symbol(market: str, code: str) -> str:
    """Tencent market + code → the symbol Xueqiu uses in URLs and its API."""
    market = market.lower()
    if market in ("sh", "sz", "bj"):
        return market.upper() + code
    if market == "hk":
        return code
    return code.split(".")[0].upper()


def _import_from_browser() -> bool:
    """Sync the reused Xueqiu site session into the existing native API client."""
    global _cookies_initialized
    from agent_reach.runtime import browser, cdp

    if not browser.is_running():
        return False
    jar = {c["name"]: c["value"] for c in cdp.cookies("xueqiu.com")}
    if "xq_a_token" not in jar:
        return False
    from agent_reach.config import Config

    Config().set("xueqiu_cookie", "; ".join(f"{k}={v}" for k, v in jar.items()))
    _cookie_jar.clear()
    _cookies_initialized = False
    return True


def _prepare_community_session() -> None:
    from agent_reach.runtime import session_reuse

    session_reuse.prepare("xueqiu")
    _import_from_browser()


def _xq_json(url: str) -> Any:
    try:
        return _get_json(url)
    except json.JSONDecodeError:
        raise ReachError(UPSTREAM_BROKEN, "Xueqiu returned an unreadable response; login expiry was not established") from None
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise ReachError(NEED_LOGIN, "Xueqiu rejected the session", hint=_XQ_LOGIN_HINT) from None
        if exc.code == 400 and _error_code(exc) == "400016":  # Xueqiu: login token missing or expired
            raise ReachError(NEED_LOGIN, "Xueqiu requires a logged-in session", hint=_XQ_LOGIN_HINT) from None
        raise


def _error_code(exc: urllib.error.HTTPError) -> str:
    try:
        return str(json.loads(exc.read().decode("utf-8")).get("error_code", ""))
    except Exception:  # noqa: BLE001 - an unreadable body is not login evidence
        return ""


_HOT_POSTS_URL = (
    "https://xueqiu.com/v4/statuses/public_timeline_by_category.json"
    "?since_id=-1&max_id=-1&count={limit}&category=-1"
)


def _parse_hot_posts(data: Any, limit: int) -> list:
    """Each list item carries a JSON-encoded `data` field with the real post."""
    results = []
    for item in (data.get("list") or [])[:limit]:
        try:
            post = json.loads(item["data"]) if isinstance(item.get("data"), str) else {}
        except (json.JSONDecodeError, KeyError):
            post = {}
        user = post.get("user") or {}
        text = _strip_html(post.get("text") or post.get("description") or "")
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


class XueqiuChannel(Channel):
    name = "xueqiu"
    description = "雪球股票行情与社区动态"

    level = "optional"
    login_url = "https://xueqiu.com/"
    logout_keys = ("xueqiu_cookie",)

    def sync_login(self):
        if not _import_from_browser():
            raise ReachError(
                NEED_LOGIN, "no Xueqiu session found in the Agent Reach browser",
                hint="Run `agent-reach login xueqiu`, let the user open xueqiu.com there, then `agent-reach login xueqiu --sync`.",
            )
        return {"synced": "xueqiu_cookie"}

    actions = (
        Action(
            "quote",
            "Real-time stock quote (A-share, HK, US)",
            (Param("symbol", "e.g. SH600519, 600519, 00700, AAPL"),),
            (("tencent", "_tencent_quote"), ("xueqiu-api", "_xq_quote")),
            live_test={"symbol": "SH600519"},
        ),
        Action(
            "search",
            "Find stocks by name or code",
            (
                Param("query", "name or code, e.g. 茅台"),
                Param("limit", "max results", required=False, type=int, default=5),
            ),
            (("tencent", "_tencent_search"), ("xueqiu-api", "_xq_search")),
            live_test={"query": "茅台", "limit": 3},
        ),
        Action(
            "hot_posts",
            "Trending Xueqiu community posts (needs a browser session)",
            (Param("limit", "max items", required=False, type=int, default=10),),
            (("xueqiu-api", "_xq_hot_posts"),),
            live_test={"limit": 3},
        ),
        Action(
            "hot_stocks",
            "Most-watched stocks on Xueqiu (needs a browser session)",
            (Param("limit", "max items", required=False, type=int, default=10),),
            (("xueqiu-api", "_xq_hot_stocks"),),
            live_test={"limit": 3},
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "xueqiu.com")

    # ── unified entry backends ──

    def _tencent_quote(self, *, symbol: str, timeout: float) -> list:
        code = _tencent_code(symbol)
        body = http_request(f"https://qt.gtimg.cn/q={code}", timeout=timeout).decode("gbk", errors="replace")
        m = re.search(r'="([^"]*)"', body)
        if not m or m.group(1).count("~") < 34:
            raise ReachError(NOT_FOUND, f"no quote for {symbol}")
        f = m.group(1).split("~")
        xq = _xueqiu_symbol(code[:2], f[2])
        quote = {
            "symbol": xq, "name": f[1], "current": f[3], "last_close": f[4], "open": f[5],
            "chg": f[31], "percent": f[32], "high": f[33], "low": f[34], "time": f[30],
        }
        return [
            make_item(
                title=f"{f[1]} ({xq})",
                url=f"https://xueqiu.com/S/{xq}",
                text=f"{f[1]} {f[3]} ({f[32]}%)",
                raw=quote,
            )
        ]

    def _tencent_search(self, *, query: str, limit: int, timeout: float) -> list:
        q = urllib.parse.quote(query)
        body = http_request(f"https://smartbox.gtimg.cn/s3/?v=2&q={q}&t=all", timeout=timeout).decode("utf-8", errors="replace")
        m = re.search(r'="([^"]*)"', body)
        if not m or m.group(1) in ("", "N"):
            return []
        items = []
        for entry in json.loads(f'"{m.group(1)}"').split("^")[:limit]:
            parts = entry.split("~")
            if len(parts) < 3:
                continue
            market, code, name = parts[0], parts[1], parts[2]
            xq = _xueqiu_symbol(market, code)
            items.append(
                make_item(
                    title=f"{name} ({xq})",
                    url=f"https://xueqiu.com/S/{xq}",
                    raw={"symbol": xq, "name": name, "market": market, "type": parts[4] if len(parts) > 4 else None},
                )
            )
        return items

    def _xq_quote(self, *, symbol: str, timeout: float) -> list:
        code = _tencent_code(symbol)
        xq = _xueqiu_symbol(code[:2], code[2:])
        data = _xq_json(f"https://stock.xueqiu.com/v5/stock/quote.json?symbol={urllib.parse.quote(xq)}&extend=detail")
        q = (data.get("data") or {}).get("quote")
        if not q:
            raise ReachError(NOT_FOUND, f"no quote for {symbol}")
        return [
            make_item(
                title=f"{q.get('name')} ({q.get('symbol')})",
                url=f"https://xueqiu.com/S/{q.get('symbol')}",
                text=f"{q.get('name')} {q.get('current')} ({q.get('percent')}%)",
                raw=q,
            )
        ]

    def _xq_search(self, *, query: str, limit: int, timeout: float) -> list:
        data = _xq_json(f"https://xueqiu.com/stock/search.json?code={urllib.parse.quote(query)}&size={limit}")
        return [
            make_item(title=f"{s.get('name')} ({s.get('code')})", url=f"https://xueqiu.com/S/{s.get('code')}", raw=s)
            for s in (data.get("stocks") or [])[:limit]
        ]

    def _xq_hot_posts(self, *, limit: int, timeout: float) -> list:
        _prepare_community_session()
        limit = max(0, min(limit, 50))
        posts = _parse_hot_posts(_xq_json(_HOT_POSTS_URL.format(limit=limit)), limit) if limit else []
        return [
            make_item(title=p["title"] or p["text"][:60], url=p["url"] or None, author=p["author"], text=p["text"], raw=p)
            for p in posts
        ]

    def _xq_hot_stocks(self, *, limit: int, timeout: float) -> list:
        _prepare_community_session()
        data = _xq_json(f"https://stock.xueqiu.com/v5/stock/hot_stock/list.json?size={limit}&type=10")
        return [
            make_item(
                title=f"{s.get('name')} ({s.get('code') or s.get('symbol')})",
                url=f"https://xueqiu.com/S/{s.get('code') or s.get('symbol')}",
                text=f"{s.get('name')} {s.get('current')} ({s.get('percent')}%)",
                raw=s,
            )
            for s in ((data.get("data") or {}).get("items") or [])[:limit]
        ]

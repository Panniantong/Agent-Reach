# -*- coding: utf-8
"""Eastmoney intent routing — news-search / query / stock-screen."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any, Literal, Optional

from agent_reach.daily_run.quote_fetch import fetch_quotes_map, normalize_code

EastmoneyIntent = Literal["news-search", "query", "stock-screen"]

_DC_REFERER = "https://data.eastmoney.com/"
_CODE_RE = re.compile(r"\b(\d{6})\b")


def eastmoney_intent_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    plugins = (settings or {}).get("plugins") or {}
    if plugins.get("eastmoney_intent_enabled") is False:
        return False
    return plugins.get("channel_enrich", True) is not False


def detect_eastmoney_intent(query: str) -> EastmoneyIntent:
    text = str(query or "").strip()
    lower = text.lower()
    if _CODE_RE.search(text):
        return "query"
    if any(token in text for token in ("筛选", "选股", "涨幅榜", "排行", "screen", "screener")):
        return "stock-screen"
    if any(token in lower for token in ("news",)) or any(
        token in text for token in ("新闻", "资讯", "公告", "研报", "消息", "热点")
    ):
        return "news-search"
    if len(text) <= 6 and text.isdigit():
        return "query"
    return "news-search"


def search_eastmoney_news(
    keyword: str,
    *,
    limit: int = 5,
    timeout: float = 15.0,
) -> list[dict[str, Any]]:
    kw = str(keyword or "").strip()
    if not kw:
        return []
    param = json.dumps(
        {
            "uid": "",
            "keyword": kw,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "1.0.0",
            "pageIndex": 1,
            "pageSize": max(1, int(limit)),
        },
        ensure_ascii=False,
    )
    url = (
        "https://search-api-web.eastmoney.com/search/jsonp"
        f"?cb=callback&param={urllib.parse.quote(param)}"
    )
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AgentReach/1.0)",
                "Referer": _DC_REFERER,
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        match = re.search(r"callback\((\{.*\})\)\s*$", raw, flags=re.S)
        if not match:
            return []
        payload = json.loads(match.group(1))
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    for item in payload.get("result") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("Title") or "").strip()
        if not title:
            continue
        rows.append(
            {
                "title": title,
                "url": item.get("url") or item.get("Url") or "",
                "date": item.get("date") or item.get("Date") or item.get("showTime") or "",
                "source": item.get("mediaName") or item.get("MediaName") or "东财",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def query_eastmoney_stock(
    query: str,
    *,
    settings: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    text = str(query or "").strip()
    if not text:
        return None
    match = _CODE_RE.search(text)
    code = normalize_code(match.group(1)) if match else normalize_code(text)
    if not code.isdigit() or len(code) != 6:
        return None
    result = fetch_quotes_map([code], settings=settings)
    row = result.quotes.get(code)
    if not row:
        return None
    return dict(row)


def screen_eastmoney_stocks(
    *,
    keyword: str = "",
    min_change_pct: float = 3.0,
    limit: int = 5,
    settings: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    plugins = (settings or {}).get("plugins") or {}
    min_pct = float(plugins.get("eastmoney_screen_min_change_pct", min_change_pct))
    max_rows = int(plugins.get("eastmoney_screen_limit", limit))
    kw = str(keyword or "").strip()

    try:
        from agent_reach.daily_run.eastmoney_market import fetch_all_stocks_resilient

        stocks, _source, _warnings = fetch_all_stocks_resilient(
            akshare_ttl=int(((settings or {}).get("akshare") or {}).get("spot_ttl", 60))
        )
    except Exception:
        stocks = []

    ranked: list[dict[str, Any]] = []
    for row in stocks:
        try:
            chg = float(row.get("change_pct") or 0)
        except (TypeError, ValueError):
            continue
        if chg < min_pct:
            continue
        name = str(row.get("name") or row.get("code") or "")
        code = normalize_code(str(row.get("code") or ""))
        if kw and kw not in name and kw not in code:
            continue
        ranked.append(
            {
                "code": code,
                "name": name,
                "change_pct": chg,
                "price": row.get("price"),
                "industry": row.get("industry") or "",
                "source": row.get("source") or "eastmoney",
            }
        )
    ranked.sort(key=lambda item: float(item.get("change_pct") or 0), reverse=True)
    return ranked[: max(1, max_rows)]


def _fetch_eastmoney_intent(
    query: str,
    *,
    use_intent: EastmoneyIntent,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    plugins = (settings or {}).get("plugins") or {}
    out: dict[str, Any] = {"intent": use_intent, "query": str(query or "").strip(), "items": []}

    if use_intent == "query":
        row = query_eastmoney_stock(query, settings=settings)
        if row:
            out["items"] = [row]
        return out

    if use_intent == "stock-screen":
        out["items"] = screen_eastmoney_stocks(keyword=query, settings=settings)
        return out

    out["items"] = search_eastmoney_news(query, limit=int(plugins.get("eastmoney_news_limit", 5)))
    return out


def route_eastmoney_intent(
    query: str,
    *,
    intent: Optional[EastmoneyIntent] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not eastmoney_intent_enabled(settings):
        return {"intent": intent or "news-search", "skipped": True, "reason": "disabled", "items": []}

    use_intent: EastmoneyIntent = intent or detect_eastmoney_intent(query)
    query_s = str(query or "").strip()

    from agent_reach.daily_run.intent_cache import (
        check_rate_limit,
        get_cached_intent,
        intent_config,
        put_cached_intent,
        record_intent_call,
    )

    cache_cfg = intent_config(settings)
    if cache_cfg["enabled"]:
        cached = get_cached_intent(use_intent, query_s, settings=settings)
        if cached is not None:
            hit = dict(cached)
            hit["from_cache"] = True
            return hit

        allowed, reason = check_rate_limit(settings)
        if not allowed:
            stale = get_cached_intent(use_intent, query_s, settings=settings, ignore_ttl=True)
            if stale is not None:
                hit = dict(stale)
                hit["from_cache"] = True
                hit["rate_limited"] = True
                return hit
            return {
                "intent": use_intent,
                "query": query_s,
                "items": [],
                "skipped": True,
                "reason": reason,
            }

    out = _fetch_eastmoney_intent(query_s, use_intent=use_intent, settings=settings)

    if cache_cfg["enabled"] and not out.get("skipped"):
        record_intent_call(settings)
        put_cached_intent(use_intent, query_s, out, settings=settings)

    return out


def format_eastmoney_intent_summary(result: dict[str, Any], *, limit: int = 2) -> str:
    if result.get("skipped"):
        return ""
    intent = str(result.get("intent") or "news-search")
    items = list(result.get("items") or [])
    if not items:
        return ""

    if intent == "query":
        row = items[0]
        name = row.get("name") or row.get("code")
        code = row.get("code") or ""
        chg = row.get("change_pct")
        chg_s = f" {float(chg):+.2f}%" if chg is not None else ""
        pe = row.get("pe_ttm")
        pe_s = f" PE {float(pe):.1f}" if pe is not None else ""
        return f"东财行情：{name}({code}){chg_s}{pe_s}"

    if intent == "stock-screen":
        parts = []
        for row in items[:limit]:
            name = row.get("name") or row.get("code")
            chg = row.get("change_pct")
            chg_s = f"{float(chg):+.1f}%" if chg is not None else "—"
            parts.append(f"{name}{chg_s}")
        return "东财选股：" + " · ".join(parts)

    parts = []
    for row in items[:limit]:
        title = str(row.get("title") or "").strip()
        if title:
            parts.append(title[:36])
    if not parts:
        return ""
    return "东财资讯：" + " | ".join(parts)


def eastmoney_macro_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    plugins = (settings or {}).get("plugins") or {}
    if plugins.get("eastmoney_macro_enabled") is False:
        return False
    return eastmoney_intent_enabled(settings)


def macro_eastmoney_query(
    portfolio: dict[str, Any],
    signals: Optional[dict[str, Any]] = None,
) -> str:
    signals = signals or {}
    for row in signals.get("hot_topics_matched") or signals.get("hot_topics") or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or row.get("topic") or "").strip()
        if title:
            return title[:32]
    for row in signals.get("portfolio_hot_stocks") or []:
        if isinstance(row, dict) and row.get("name"):
            return str(row["name"])[:32]
    for row in portfolio.get("holdings") or []:
        if isinstance(row, dict) and row.get("name"):
            return str(row["name"])[:32]
    return "A股 热点"


def attach_eastmoney_macro_context(
    signals: dict[str, Any],
    sources: dict[str, Any],
    portfolio: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> None:
    if not eastmoney_macro_enabled(settings):
        return
    query = macro_eastmoney_query(portfolio, signals)
    result = route_eastmoney_intent(query, settings=settings)
    summary = format_eastmoney_intent_summary(result, limit=3)
    if not summary:
        return
    signals["eastmoney_intent"] = result
    sources["eastmoney"] = {
        "summary": summary,
        "backend": "eastmoney_intent",
        "intent": result.get("intent"),
        "query": query,
    }


def attach_eastmoney_market_review(
    review: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> None:
    if not eastmoney_macro_enabled(settings):
        return
    sa = review.get("sector_analysis") or {}
    main_sectors = sa.get("main_sectors") or []
    query = str((main_sectors[0] or {}).get("name") or "").strip() if main_sectors else ""
    if not query:
        query = "A股"
    result = route_eastmoney_intent(f"{query} 资讯", settings=settings)
    summary = format_eastmoney_intent_summary(result, limit=3)
    if not summary:
        return
    review["eastmoney_intent"] = result
    review["eastmoney_summary"] = summary


def render_eastmoney_macro_markdown(
    *,
    macro_signals: Optional[dict[str, Any]] = None,
    sources: Optional[dict[str, Any]] = None,
    market_review: Optional[dict[str, Any]] = None,
) -> str:
    if market_review and market_review.get("eastmoney_summary"):
        return "**东财路由**\n\n" + str(market_review["eastmoney_summary"])
    result = (macro_signals or {}).get("eastmoney_intent")
    if isinstance(result, dict) and result.get("items"):
        summary = format_eastmoney_intent_summary(result, limit=3)
        if summary:
            return f"**东财路由**\n\n{summary}"
    em = (sources or {}).get("eastmoney")
    if isinstance(em, dict) and em.get("summary"):
        return f"**东财路由**\n\n{em['summary']}"
    return ""

# -*- coding: utf-8
"""Xueqiu stock search — resolve hot-topic keywords to A-share symbols."""

from __future__ import annotations

from typing import Any, Optional

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger("agent_reach.daily_run.xueqiu_stock_search")


def xueqiu_stock_search_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    cfg = settings or {}
    macro = cfg.get("macro_collector") or {}
    nested = macro.get("xueqiu_stock_search") or {}
    if nested.get("enabled") is False:
        return False
    return macro.get("xueqiu_stock_search_enabled", True) is not False


def _search_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    macro = (settings or {}).get("macro_collector") or {}
    nested = macro.get("xueqiu_stock_search") or {}
    return {
        "result_limit": int(nested.get("result_limit", macro.get("xueqiu_stock_search_limit", 3))),
        "query_limit": int(
            nested.get("query_limit", macro.get("xueqiu_stock_search_query_limit", 2))
        ),
        "per_query": int(
            nested.get("per_query", macro.get("xueqiu_stock_search_per_query", 2))
        ),
    }


def is_a_share_symbol(symbol: str) -> bool:
    from agent_reach.daily_run.xueqiu_hot_display import normalize_xueqiu_symbol

    text = str(symbol or "").strip().upper()
    if not text.startswith(("SH", "SZ", "BJ")):
        return False
    code = normalize_xueqiu_symbol(text)
    return len(code) == 6 and code.isdigit()


def search_row_to_match(
    row: dict[str, Any],
    *,
    query: str,
    source_title: str = "",
) -> Optional[dict[str, Any]]:
    from agent_reach.daily_run.xueqiu_hot_display import normalize_xueqiu_symbol

    symbol = str(row.get("symbol") or "").strip()
    if not is_a_share_symbol(symbol):
        return None
    code = normalize_xueqiu_symbol(symbol)
    name = str(row.get("name") or code).strip()
    return {
        "code": code,
        "name": name,
        "symbol": symbol,
        "exchange": row.get("exchange"),
        "query": query,
        "source_title": source_title[:120] if source_title else "",
    }


def search_xueqiu_stocks(
    query: str,
    *,
    limit: int = 5,
    settings: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    if not query or not xueqiu_stock_search_enabled(settings):
        return []
    try:
        from agent_reach.channels import xueqiu as xq_mod

        xq_mod._ensure_cookies()
        ch = xq_mod.XueqiuChannel()
        rows = ch.search_stock(str(query).strip(), limit=max(1, min(int(limit), 10)))
        return [r for r in rows if isinstance(r, dict)]
    except Exception as exc:
        logger.warning("xueqiu search_stock failed for {}: {}", query, exc)
        return []


def _portfolio_codes(portfolio: dict[str, Any]) -> set[str]:
    from agent_reach.daily_run.snapshot_builder import _normalize_code

    codes: set[str] = set()
    for row in (portfolio.get("holdings") or []) + (portfolio.get("watchlist") or []):
        if isinstance(row, dict) and row.get("code"):
            codes.add(_normalize_code(str(row["code"])))
    return codes


def _title_buckets(signals: dict[str, Any]) -> list[tuple[str, str]]:
    buckets: list[tuple[str, str]] = []
    for item in signals.get("hot_topics_matched") or []:
        if isinstance(item, dict) and item.get("title"):
            buckets.append(("60s", str(item["title"])))
    for item in signals.get("redfox_matched") or []:
        if isinstance(item, dict) and item.get("title"):
            buckets.append(("redfox", str(item["title"])))
    for item in signals.get("sentiment_hits") or signals.get("sentiment_posts") or []:
        if isinstance(item, dict):
            title = str(item.get("title") or (item.get("text") or "")[:80]).strip()
            if title:
                buckets.append(("xueqiu", title))
    return buckets


def extract_search_queries(
    signals: dict[str, Any],
    portfolio: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> list[dict[str, str]]:
    from agent_reach.daily_run.hot_news_collector import portfolio_keywords

    titles = _title_buckets(signals)
    if not titles:
        return []

    keywords = portfolio_keywords(portfolio, settings)
    cfg = _search_cfg(settings)
    queries: list[dict[str, str]] = []
    seen_queries: set[str] = set()

    for source, title in titles:
        for kw in keywords:
            token = str(kw or "").strip()
            if len(token) < 2 or token.isdigit():
                continue
            if token not in title:
                continue
            if token in seen_queries:
                continue
            seen_queries.add(token)
            queries.append({"query": token, "source": source, "title": title[:120]})
            if len(queries) >= cfg["query_limit"]:
                return queries
    return queries


def attach_xueqiu_stock_search(
    signals: dict[str, Any],
    portfolio: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Search Xueqiu for hot-topic keywords and attach A-share discovery rows."""
    if not xueqiu_stock_search_enabled(settings):
        signals.pop("xueqiu_stock_search", None)
        return signals

    query_rows = extract_search_queries(signals, portfolio, settings=settings)
    if not query_rows:
        signals.pop("xueqiu_stock_search", None)
        return signals

    cfg = _search_cfg(settings)
    skip_codes = _portfolio_codes(portfolio)
    for match in (signals.get("portfolio_hot_stocks") or []) + (signals.get("portfolio_hot_posts") or []):
        if isinstance(match, dict) and match.get("code"):
            skip_codes.add(str(match["code"]))

    matches: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for row in query_rows:
        query = row["query"]
        hits = search_xueqiu_stocks(query, limit=cfg["per_query"], settings=settings)
        for hit in hits:
            match = search_row_to_match(
                hit,
                query=query,
                source_title=row.get("title") or "",
            )
            if not match:
                continue
            code = match["code"]
            if code in skip_codes or code in seen_codes:
                continue
            match["source"] = row.get("source") or "hot_topic"
            matches.append(match)
            seen_codes.add(code)
            if len(matches) >= cfg["result_limit"]:
                break
        if len(matches) >= cfg["result_limit"]:
            break

    if matches:
        signals["xueqiu_stock_search"] = matches
    else:
        signals.pop("xueqiu_stock_search", None)
    return signals


def xueqiu_stock_search_summary(
    macro_signals: Optional[dict[str, Any]],
    *,
    limit: int = 2,
) -> str:
    rows = (macro_signals or {}).get("xueqiu_stock_search") or []
    if not rows:
        return ""
    parts = []
    for row in rows[:limit]:
        name = row.get("name") or row.get("code")
        query = row.get("query")
        parts.append(f"{name}({query})" if query else str(name))
    return "热点搜股：" + "；".join(parts)


def render_xueqiu_stock_search_markdown(
    rows: Optional[list[dict[str, Any]]] = None,
    *,
    limit: int = 3,
) -> str:
    items = list(rows or [])
    if not items:
        return ""
    lines = ["**热点关键词搜股**", ""]
    for row in items[:limit]:
        name = row.get("name") or row.get("code") or "—"
        code = row.get("code") or "—"
        query = row.get("query") or "—"
        source = row.get("source") or "hot_topic"
        title = str(row.get("source_title") or "").strip()
        title_s = f" · {title[:28]}" if title else ""
        lines.append(f"- **{name}** ({code}) ← 「{query}」[{source}]{title_s}")
    return "\n".join(lines)

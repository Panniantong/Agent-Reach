# -*- coding: utf-8
"""Exa deep research triggered by Xueqiu portfolio hot-stock/post overlaps."""

from __future__ import annotations

from typing import Any, Optional


def build_xueqiu_overlap_exa_queries(
    macro_signals: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> list[dict[str, str]]:
    from agent_reach.daily_run.settings import effective_settings, load_settings

    cfg = effective_settings(settings or load_settings())
    collector_cfg = cfg.get("macro_collector") or {}
    if collector_cfg.get("xueqiu_exa_research_enabled", True) is False:
        return []

    max_q = int(collector_cfg.get("xueqiu_exa_max_queries", 2))
    queries: list[dict[str, str]] = []
    seen: set[str] = set()

    if collector_cfg.get("intraday_exa_new_hot_enabled", True) is not False:
        for match in macro_signals.get("portfolio_hot_stocks_new") or []:
            if not isinstance(match, dict):
                continue
            code = str(match.get("code") or "").strip()
            name = str(match.get("name") or code).strip()
            if not code or code in seen:
                continue
            seen.add(code)
            board = str(match.get("board") or "热股")
            rank = match.get("rank")
            rank_s = f" rank {rank}" if rank is not None else ""
            role = "holding" if match.get("role") == "holding" else "watchlist"
            queries.append(
                {
                    "type": "xueqiu_hot_stock_new",
                    "code": code,
                    "label": f"{name} · 新登{board}",
                    "query": (
                        f"{name} {code} China A-share newly trending xueqiu hot board "
                        f"latest news catalyst sentiment outlook 2026"
                    ),
                    "trigger": f"New {role} on Xueqiu {board}{rank_s}",
                }
            )
            if len(queries) >= max_q:
                return queries

    for match in macro_signals.get("portfolio_hot_stocks") or []:
        if not isinstance(match, dict):
            continue
        code = str(match.get("code") or "").strip()
        name = str(match.get("name") or code).strip()
        if not code or code in seen:
            continue
        seen.add(code)
        board = str(match.get("board") or "热股")
        rank = match.get("rank")
        rank_s = f" rank {rank}" if rank is not None else ""
        role = "holding" if match.get("role") == "holding" else "watchlist"
        queries.append(
            {
                "type": "xueqiu_hot_stock",
                "code": code,
                "label": f"{name} · 雪球{board}",
                "query": (
                    f"{name} {code} China A-share latest news earnings sentiment "
                    f"competitors outlook 2026 xueqiu hot stock"
                ),
                "trigger": f"{role} on Xueqiu {board}{rank_s}",
            }
        )
        if len(queries) >= max_q:
            return queries

    for post in macro_signals.get("portfolio_hot_posts") or []:
        if not isinstance(post, dict):
            continue
        title = str(post.get("title") or (post.get("text") or "")[:48]).strip()
        if not title:
            continue
        key = str(post.get("url") or post.get("id") or title[:32])
        if key in seen:
            continue
        seen.add(key)
        kws = post.get("matched_keywords") or []
        kw_s = " ".join(str(k) for k in kws[:2])
        queries.append(
            {
                "type": "xueqiu_hot_post",
                "label": f"雪球热帖 · {title[:24]}",
                "query": f"China A-share {kw_s} {title[:80]} market impact outlook 2026",
                "trigger": f"Xueqiu hot post: {title[:48]}",
            }
        )
        if len(queries) >= max_q:
            break

    if collector_cfg.get("xueqiu_exa_search_research_enabled", True) is not False:
        for row in macro_signals.get("xueqiu_stock_search") or []:
            if not isinstance(row, dict):
                continue
            code = str(row.get("code") or "").strip()
            name = str(row.get("name") or code).strip()
            if not code or code in seen:
                continue
            seen.add(code)
            query_kw = str(row.get("query") or "")
            queries.append(
                {
                    "type": "xueqiu_hot_search",
                    "code": code,
                    "label": f"{name} · 热点搜股",
                    "query": (
                        f"{name} {code} China A-share {query_kw} latest news earnings "
                        f"competitors outlook 2026 hot topic discovery"
                    ),
                    "trigger": f"Hot-topic search 「{query_kw}」→ {name}",
                }
            )
            if len(queries) >= max_q:
                break

    return queries[:max_q]


def run_xueqiu_overlap_exa_research(
    macro_signals: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from agent_reach.daily_run.exa_client import ExaError, is_exa_available, summarize_hits

    queries = build_xueqiu_overlap_exa_queries(macro_signals, settings=settings)
    if not queries or not is_exa_available():
        return []

    from agent_reach.daily_run.settings import effective_settings, load_settings

    cfg = effective_settings(settings or load_settings())
    plugin_cfg = cfg.get("plugins") or {}
    timeout = int(plugin_cfg.get("exa_timeout", 45))

    def _run_one(q: dict[str, str]) -> dict[str, Any]:
        try:
            from agent_reach.daily_run.exa_cache import cached_web_search_exa

            hits, _cached = cached_web_search_exa(
                q["query"],
                num_results=3,
                timeout=timeout,
                settings=cfg,
            )
            return {**q, "hits": hits, "summary": summarize_hits(hits), "success": True}
        except ExaError as exc:
            return {**q, "hits": [], "summary": str(exc), "success": False}

    workers = min(len(queries), 2)
    ordered: list[Optional[dict[str, Any]]] = [None] * len(queries)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_one, q): i for i, q in enumerate(queries)}
        for fut in as_completed(futures):
            ordered[futures[fut]] = fut.result()
    return [r for r in ordered if r is not None]


def attach_xueqiu_exa_research(
    signals: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    triggers = (
        (signals.get("portfolio_hot_stocks_new") or [])
        + (signals.get("portfolio_hot_stocks") or [])
        + (signals.get("portfolio_hot_posts") or [])
        + (signals.get("xueqiu_stock_search") or [])
    )
    if not triggers:
        signals.pop("xueqiu_exa_research", None)
        return signals
    results = run_xueqiu_overlap_exa_research(signals, settings=settings)
    if results:
        signals["xueqiu_exa_research"] = results
    else:
        signals.pop("xueqiu_exa_research", None)
    return signals

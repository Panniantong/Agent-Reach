# -*- coding: utf-8
"""Channel-backed enrichment for expert plugins."""

from __future__ import annotations

from typing import Any, Optional


def search_exa_snippet(query: str, settings: dict[str, Any]) -> Optional[str]:
    cfg = settings.get("plugins", {})
    if not cfg.get("channel_enrich", True):
        return None
    max_q = int(cfg.get("max_exa_queries_per_expert", 1))
    if max_q <= 0:
        return None
    try:
        from agent_reach.daily_run.exa_client import summarize_hits
        from agent_reach.daily_run.intent_cache import run_intent_cached

        def _fetch() -> dict[str, Any]:
            from agent_reach.daily_run.exa_cache import cached_web_search_exa

            hits, _from_exa_cache = cached_web_search_exa(
                query,
                num_results=2,
                timeout=int(cfg.get("exa_timeout", 30)),
                settings=settings,
            )
            snippet = summarize_hits(hits) or ""
            return {
                "intent": "exa-search",
                "query": query,
                "snippet": snippet,
                "hits": hits,
            }

        result = run_intent_cached("exa-search", query, _fetch, settings=settings)
        if result.get("skipped"):
            return None
        return str(result.get("snippet") or "").strip() or None
    except Exception:
        return None


def fetch_xueqiu_hot_summary(limit: int = 3) -> Optional[str]:
    try:
        from agent_reach.channels import xueqiu as xq_mod

        xq_mod._ensure_cookies()
        ch = xq_mod.XueqiuChannel()
        posts = ch.get_hot_posts(limit=limit)
        if not posts:
            return None
        parts = [p.get("title") or p.get("text", "")[:40] for p in posts[:limit]]
        return "雪球：" + " | ".join(p for p in parts if p)
    except Exception:
        return None


def hot_news_summary_from_snapshot(snapshot: dict[str, Any]) -> Optional[str]:
    """Return pre-collected hot news text from snapshot sources (no network)."""
    sources = snapshot.get("sources") or {}
    hot = sources.get("hot_news")
    if not isinstance(hot, dict):
        return None
    text = hot.get("text_feed") or hot.get("summary") or hot.get("detail")
    return str(text).strip() or None


def fetch_eastmoney_intent_snippet(
    snapshot: dict[str, Any],
    settings: dict[str, Any],
) -> Optional[str]:
    from agent_reach.daily_run.eastmoney_intent import (
        format_eastmoney_intent_summary,
        route_eastmoney_intent,
    )

    query = str(snapshot.get("name") or snapshot.get("code") or "").strip()
    if not query:
        return None
    result = route_eastmoney_intent(query, settings=settings)
    return format_eastmoney_intent_summary(result) or None


def score_from_text(text: str, base: float = 50.0) -> float:
    """Heuristic sentiment score from text keywords."""
    if not text:
        return base
    t = text.lower()
    pos = sum(1 for w in ("涨", "流入", "利好", "突破", "growth", "beat", "surge") if w in t)
    neg = sum(1 for w in ("跌", "流出", "利空", "暴跌", "risk", "miss", "drop", "制裁") if w in t)
    return max(0.0, min(100.0, base + (pos - neg) * 4))

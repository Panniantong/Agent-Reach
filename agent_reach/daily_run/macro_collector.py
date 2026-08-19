# -*- coding: utf-8
"""Live macro / flow / sentiment collection for daily-run snapshots."""

from __future__ import annotations

from typing import Any, Optional


def collect_macro_context(
    portfolio: dict[str, Any],
    *,
    config=None,
    settings: Optional[dict[str, Any]] = None,
    workflow: str = "morning",
) -> dict[str, Any]:
    """
    Collect macro signals and derive mss_breakdown + sources.

    Priority: live APIs → portfolio overrides → static defaults.
    """
    from agent_reach.daily_run.settings import load_settings

    cfg = settings or load_settings()
    collector_cfg = cfg.get("macro_collector", {})
    overrides = portfolio.get("sources_overrides") or {}
    base_breakdown = dict(portfolio.get("mss_breakdown") or {})

    signals: dict[str, Any] = {
        "index_change_pct": None,
        "northbound_flow_yi": None,
        "sentiment_posts": [],
        "hot_topics": [],
        "hot_topics_matched": [],
        "hot_topic_hits": 0,
    }
    sources: dict[str, Any] = {}

    # --- Index (global proxy) ---
    index_change = _fetch_index_change()
    if index_change is not None:
        signals["index_change_pct"] = index_change
        sources["quote"] = {
            "summary": f"上证 {index_change:+.2f}%",
            "backend": "macro_collector",
        }

    # --- Northbound flow ---
    flow_yi = _fetch_northbound_flow()
    if flow_yi is not None:
        signals["northbound_flow_yi"] = flow_yi
        direction = "净流入" if flow_yi >= 0 else "净流出"
        sources["flow"] = {
            "summary": f"北向资金{direction} {abs(flow_yi):.2f} 亿",
            "backend": "macro_collector",
        }

    # --- Xueqiu sentiment ---
    sentiment_summary, posts = _fetch_xueqiu_sentiment(
        portfolio, limit=int(collector_cfg.get("sentiment_post_limit", 5))
    )
    if sentiment_summary:
        signals["sentiment_posts"] = posts
        sources["sentiment"] = {
            "summary": sentiment_summary,
            "backend": "xueqiu",
        }

    # --- Multi-platform hot news (60s API) ---
    hot_summary = ""
    hot_headline = ""
    try:
        from agent_reach.daily_run.hot_news_collector import collect_hot_news

        hot = collect_hot_news(portfolio, settings=cfg)
        if hot.items:
            signals["hot_topics"] = hot.items
            signals["hot_topics_matched"] = hot.matched
            signals["hot_topic_hits"] = len(hot.matched)
            hot_summary = hot.summary
            hot_headline = hot.headline_summary
            sources["hot_news"] = {
                "summary": hot.summary or hot.headline_summary,
                "backend": "60s_api",
                "platforms": hot.platforms_ok,
                "text_feed": hot.text_feed,
            }
            if hot.text_feed:
                sources["hot_news"]["detail"] = hot.text_feed[:2000]
    except Exception:
        pass

    # --- RedFox API (optional Path B) ---
    try:
        from agent_reach.daily_run.redfox_collector import collect_redfox_context, redfox_enabled

        if redfox_enabled(cfg):
            redfox = collect_redfox_context(portfolio, settings=cfg, workflow=workflow)
            if redfox.summary or redfox.gzh_summary or redfox.matched or redfox.stock_feed_items:
                signals["redfox"] = redfox.to_dict()
                signals["redfox_matched"] = redfox.matched
                signals["redfox_hits"] = len(redfox.matched)
                detail_parts = [p for p in (redfox.gzh_summary, redfox.summary) if p]
                sources["redfox"] = {
                    "summary": "；".join(detail_parts)[:240] or redfox.summary,
                    "backend": "redfox_api",
                    "platforms": redfox.platforms_ok,
                    "matched_count": len(redfox.matched),
                }
                if redfox.errors:
                    sources["redfox"]["warnings"] = redfox.errors[:3]
    except Exception as exc:
        try:
            from loguru import logger

            logger.warning("redfox macro collection failed: {}", exc)
        except ImportError:
            pass
        if redfox_enabled(cfg):
            sources["redfox"] = {
                "summary": f"RedFox 采集失败: {exc}"[:120],
                "backend": "redfox_api",
                "error": str(exc),
            }

    # Merge portfolio overrides (non-placeholder only)
    for cat, detail in overrides.items():
        if isinstance(detail, dict) and not _is_placeholder(detail.get("summary", "")):
            sources[cat] = dict(detail)

    breakdown = _derive_mss_breakdown(base_breakdown, signals, cfg)

    macro_parts = []
    if hot_headline:
        macro_parts.append(hot_headline[:60])
    elif hot_summary:
        macro_parts.append(hot_summary[:60])
    if index_change is not None:
        macro_parts.append(f"大盘 {index_change:+.2f}%")
    if flow_yi is not None:
        macro_parts.append(f"北向 {flow_yi:+.2f}亿")
    if sentiment_summary:
        macro_parts.append(sentiment_summary[:40])
    elif hot_summary and not hot_headline:
        pass
    elif hot_summary:
        macro_parts.append(hot_summary[:40])
    redfox_src = sources.get("redfox")
    if isinstance(redfox_src, dict) and redfox_src.get("summary"):
        macro_parts.append(str(redfox_src["summary"])[:60])

    macro_summary = portfolio.get("macro_summary")
    if macro_parts:
        live_summary = "；".join(macro_parts)
        macro_summary = live_summary if not macro_summary else f"{live_summary} | {macro_summary}"

    return {
        "mss_breakdown": breakdown,
        "sources": sources,
        "macro_summary": macro_summary,
        "macro_signals": signals,
    }


def threshold_refs_for_display(settings: dict[str, Any]) -> dict[str, float]:
    """Effective macro veto / aggressive entry refs for reports (harness overlay aware)."""
    from agent_reach.daily_run.harness_policy import aggressive_entry_default, macro_veto_default
    from agent_reach.daily_run.settings import effective_settings

    eff = effective_settings(settings)
    return {
        "_macro_veto_ref": macro_veto_default(eff),
        "_aggressive_ref": aggressive_entry_default(eff),
    }


def apply_threshold_refs(breakdown: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    """Refresh _macro_veto_ref / _aggressive_ref on an existing breakdown (e.g. daily cache)."""
    out = dict(breakdown or {})
    out.update(threshold_refs_for_display(settings))
    return out


def _derive_mss_breakdown(
    base: dict[str, Any],
    signals: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, float]:
    """Map live signals to MSS factor scores 0-100."""

    fx = float(base.get("fx", 50))
    flow = float(base.get("flow", 50))
    global_score = float(base.get("global", 50))
    sentiment = float(base.get("sentiment", 50))

    idx = signals.get("index_change_pct")
    if idx is not None:
        global_score = _clamp(50 + float(idx) * 8)
        fx = _clamp(50 + float(idx) * 5)

    nb = signals.get("northbound_flow_yi")
    if nb is not None:
        flow = _clamp(50 + float(nb) * 2.5)

    posts = signals.get("sentiment_posts") or []
    if posts:
        sentiment = _clamp(50 + len(posts) * 3)

    hot_cfg = settings.get("hot_news") or {}
    hot_hits = int(signals.get("hot_topic_hits") or 0)
    if hot_hits:
        boost = float(hot_cfg.get("sentiment_boost_per_hit", 2))
        sentiment = _clamp(sentiment + hot_hits * boost)

    redfox_hits = int(signals.get("redfox_hits") or 0)
    if redfox_hits:
        rf_cfg = settings.get("redfox") or {}
        boost = float(rf_cfg.get("sentiment_boost_per_hit", 1.5))
        sentiment = _clamp(sentiment + redfox_hits * boost)

    breakdown = {
        "fx": round(fx, 1),
        "flow": round(flow, 1),
        "global": round(global_score, 1),
        "sentiment": round(sentiment, 1),
    }
    breakdown.update(threshold_refs_for_display(settings))
    return breakdown


def _fetch_index_change() -> Optional[float]:
    try:
        from agent_reach.channels import xueqiu as xq_mod

        xq_mod._ensure_cookies()
        ch = xq_mod.XueqiuChannel()
        q = ch.get_stock_quote("SH000001")
        pct = q.get("percent")
        return float(pct) if pct is not None else None
    except Exception:
        pass
    try:
        from agent_reach.daily_run.akshare_adapter import fetch_quote

        q = fetch_quote("000001")
        return float(q.get("change_pct", 0))
    except Exception:
        return None


def _fetch_northbound_flow() -> Optional[float]:
    try:
        from agent_reach.daily_run.akshare_adapter import _import_akshare

        ak = _import_akshare()
        df = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
        if df is not None and len(df) > 0:
            val = df.iloc[-1].get("value") or df.iloc[-1].get("当日资金流入")
            if val is not None:
                return float(val) / 1e8 if float(val) > 1e6 else float(val)
    except Exception:
        pass
    return None


def _fetch_xueqiu_sentiment(
    portfolio: dict[str, Any],
    *,
    limit: int = 5,
) -> tuple[str, list[dict[str, Any]]]:
    try:
        from agent_reach.channels import xueqiu as xq_mod

        xq_mod._ensure_cookies()
        ch = xq_mod.XueqiuChannel()
        posts = ch.get_hot_posts(limit=limit)
        keywords = _portfolio_keywords(portfolio, settings=None)
        hits = []
        for p in posts:
            text = f"{p.get('title', '')} {p.get('text', '')}"
            if any(k in text for k in keywords if k):
                hits.append(p)
        if not hits:
            hits = posts[:2]
        parts = [f"{p.get('title') or p.get('text', '')[:30]}" for p in hits[:2]]
        summary = "雪球热点：" + " | ".join(parts) if parts else ""
        return summary[:200], hits
    except Exception:
        return "", []


def _portfolio_keywords(portfolio: dict[str, Any], settings: Optional[dict[str, Any]] = None) -> list[str]:
    from agent_reach.daily_run.hot_news_collector import portfolio_keywords

    return portfolio_keywords(portfolio, settings)


def _is_placeholder(text: str) -> bool:
    return not text or text.strip() in ("待更新", "pending", "n/a", "N/A")


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))

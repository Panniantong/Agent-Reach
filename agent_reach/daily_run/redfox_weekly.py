# -*- coding: utf-8
"""Weekly RedFox vs 60s hot-topic diff and market-review rollups."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any, Optional

from agent_reach.daily_run.hot_news_collector import collect_hot_news
from agent_reach.daily_run.market_review import load_market_review
from agent_reach.daily_run.redfox_collector import collect_redfox_context, redfox_enabled
from agent_reach.daily_run.trade_calendar import is_trading_day


def _norm_title(title: str) -> str:
    return " ".join(str(title or "").strip().lower().split())[:100]


def build_hot_topic_diff(
    portfolio: dict[str, Any],
    *,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Compare 60s hot list vs RedFox trending/stock-feed titles for the week context."""
    hot_cfg = settings.get("hot_news") or {}
    if hot_cfg.get("enabled") is False and not redfox_enabled(settings):
        return {}
    weekly_cfg = (settings.get("redfox") or {}).get("weekly_diff") or {}
    if weekly_cfg.get("enabled") is False:
        return {}

    items_60s: list[dict[str, Any]] = []
    items_redfox: list[dict[str, Any]] = []

    if hot_cfg.get("enabled") is not False:
        try:
            hot = collect_hot_news(portfolio, settings=settings)
            items_60s = list(hot.items or [])
        except Exception:
            pass

    if redfox_enabled(settings):
        try:
            rf = collect_redfox_context(portfolio, settings=settings, workflow="weekly")
            items_redfox = list(rf.trending_items or []) + list(rf.stock_feed_items or [])
        except Exception:
            pass

    map_60s = {_norm_title(i.get("title", "")): i for i in items_60s if i.get("title")}
    map_rf = {_norm_title(i.get("title", "")): i for i in items_redfox if i.get("title")}

    keys_60s = set(map_60s.keys())
    keys_rf = set(map_rf.keys())
    overlap_keys = keys_60s & keys_rf
    only_60s_keys = keys_60s - keys_rf
    only_rf_keys = keys_rf - keys_60s

    def _pick(keys: set[str], source: dict[str, dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for key in sorted(keys)[:limit]:
            item = source[key]
            out.append(
                {
                    "title": item.get("title"),
                    "platform": item.get("platform"),
                }
            )
        return out

    return {
        "count_60s": len(keys_60s),
        "count_redfox": len(keys_rf),
        "overlap_count": len(overlap_keys),
        "overlap": _pick(overlap_keys, {**map_60s}),
        "only_60s": _pick(only_60s_keys, map_60s),
        "only_redfox": _pick(only_rf_keys, map_rf),
    }


def render_hot_topic_diff_markdown(diff: dict[str, Any]) -> str:
    if not diff or (not diff.get("count_60s") and not diff.get("count_redfox")):
        return ""
    lines = [
        "### 🦊 RedFox vs 60s 热榜 diff",
        "",
        f"- 60s **{diff.get('count_60s', 0)}** 条 · RedFox **{diff.get('count_redfox', 0)}** 条 · 重叠 **{diff.get('overlap_count', 0)}**",
        "",
    ]
    if diff.get("overlap"):
        lines.append("**双源共识（节选）：**")
        for item in diff["overlap"][:3]:
            lines.append(f"- [{item.get('platform', '?')}] {item.get('title', '')[:50]}")
        lines.append("")
    if diff.get("only_redfox"):
        lines.append("**仅 RedFox 捕获：**")
        for item in diff["only_redfox"][:3]:
            lines.append(f"- [{item.get('platform', '?')}] {item.get('title', '')[:50]}")
        lines.append("")
    if diff.get("only_60s"):
        lines.append("**仅 60s 捕获：**")
        for item in diff["only_60s"][:3]:
            lines.append(f"- [{item.get('platform', '?')}] {item.get('title', '')[:50]}")
        lines.append("")
    return "\n".join(lines).strip()


def summarize_week_market_reviews(
    week_start: date,
    week_end: date,
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Roll up saved close market_review JSON for the trading week."""
    cfg = settings or {}
    mr_cfg = cfg.get("market_review") or {}
    if mr_cfg.get("enabled") is False:
        return {}

    mainline_types: list[str] = []
    emotion_ratings: list[str] = []
    lhb_net_total = 0.0
    days_with_data = 0

    cursor = week_start
    while cursor <= week_end:
        ok, _ = is_trading_day(cursor, settings=cfg)
        if ok:
            review = load_market_review(cursor.isoformat())
            if review and not review.get("error"):
                days_with_data += 1
                sa = review.get("sector_analysis") or {}
                mt = str(sa.get("mainline_type") or "").strip()
                if mt:
                    mainline_types.append(mt)
                em = review.get("emotion") or {}
                rating = str(em.get("rating") or "").strip()
                if rating:
                    emotion_ratings.append(rating)
                la = review.get("lhb_analysis") or {}
                summary = la.get("summary") if isinstance(la.get("summary"), dict) else la
                if isinstance(summary, dict):
                    lhb_net_total += float(summary.get("total_net") or 0)
                else:
                    lhb_net_total += float(la.get("total_net") or 0)
        cursor += timedelta(days=1)

    if days_with_data == 0:
        return {}

    type_counts = Counter(mainline_types)
    emotion_counts = Counter(emotion_ratings)
    dominant_mainline = type_counts.most_common(1)[0][0] if type_counts else "—"

    return {
        "days_with_data": days_with_data,
        "mainline_type_counts": dict(type_counts),
        "dominant_mainline": dominant_mainline,
        "emotion_counts": dict(emotion_counts),
        "lhb_net_total_yi": round(lhb_net_total, 2),
    }


def render_market_review_weekly_markdown(summary: dict[str, Any]) -> str:
    if not summary:
        return ""
    lines = [
        "### 📊 本周全市场复盘汇总",
        "",
        f"- 有效交易日 **{summary.get('days_with_data', 0)}** 天 · 主线类型以 **{summary.get('dominant_mainline', '—')}** 为主",
    ]
    ec = summary.get("emotion_counts") or {}
    if ec:
        parts = [f"{k}×{v}" for k, v in sorted(ec.items(), key=lambda x: -x[1])]
        lines.append(f"- 情绪定级分布：{' / '.join(parts)}")
    net = summary.get("lhb_net_total_yi")
    if net is not None:
        lines.append(f"- 龙虎榜累计净额 **{net:+.1f} 亿**")
    mt = summary.get("mainline_type_counts") or {}
    if len(mt) > 1:
        tags = " · ".join(f"{k}({v})" for k, v in mt.items())
        lines.append(f"- 主线标签：{tags}")
    lines.append("")
    return "\n".join(lines)

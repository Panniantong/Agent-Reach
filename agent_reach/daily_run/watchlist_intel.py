# -*- coding: utf-8
"""Watchlist strategy intel — Xueqiu announcements and news per symbol."""

from __future__ import annotations

import time
from typing import Any, Optional

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger("agent_reach.daily_run.watchlist_intel")

_DEFAULT_NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "利空",
    "减持",
    "亏损",
    "预亏",
    "立案",
    "调查",
    "警示",
    "退市",
    "终止",
    "违规",
    "处罚",
    "诉讼",
    "风险提示",
    "质押",
    "爆仓",
    "下调",
    "ST",
    "*ST",
)


def watchlist_intel_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    wl = (settings or {}).get("watchlist") or {}
    nested = wl.get("intel") or {}
    if nested.get("enabled") is False:
        return False
    return wl.get("announcement_intel_enabled", True) is not False


def _intel_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    wl = (settings or {}).get("watchlist") or {}
    nested = wl.get("intel") or {}
    raw_keywords = nested.get("negative_keywords", wl.get("negative_intel_keywords"))
    if isinstance(raw_keywords, list) and raw_keywords:
        keywords = tuple(str(k).strip() for k in raw_keywords if str(k).strip())
    else:
        keywords = _DEFAULT_NEGATIVE_KEYWORDS
    return {
        "symbol_limit": int(nested.get("symbol_limit", wl.get("intel_symbol_limit", 8))),
        "announcement_limit": int(
            nested.get("announcement_limit", wl.get("announcement_fetch_limit", 3))
        ),
        "news_limit": int(nested.get("news_limit", wl.get("news_fetch_limit", 3))),
        "lookback_days": int(nested.get("lookback_days", wl.get("announcement_lookback_days", 7))),
        "announcement_boost": float(
            nested.get("announcement_boost", wl.get("announcement_score_boost", 3))
        ),
        "news_boost": float(nested.get("news_boost", wl.get("news_score_boost", 1))),
        "negative_announcement_penalty": float(
            nested.get(
                "negative_announcement_penalty",
                wl.get("negative_announcement_penalty", -4),
            )
        ),
        "negative_news_penalty": float(
            nested.get("negative_news_penalty", wl.get("negative_news_penalty", -2))
        ),
        "negative_intel_remove_enabled": nested.get(
            "negative_remove_enabled",
            wl.get("negative_intel_remove_enabled", True),
        )
        is not False,
        "include_candidates": nested.get("include_candidates", wl.get("intel_include_candidates", True))
        is not False,
        "candidate_limit": int(nested.get("candidate_limit", wl.get("intel_candidate_limit", 5))),
        "negative_keywords": keywords,
    }


def _within_lookback(created_at: Any, *, lookback_days: int) -> bool:
    if created_at is None or lookback_days <= 0:
        return True
    try:
        ts = float(created_at)
    except (TypeError, ValueError):
        return True
    if ts > 1e12:
        ts /= 1000.0
    cutoff = time.time() - lookback_days * 86400
    return ts >= cutoff


def _filter_recent(items: list[dict[str, Any]], *, lookback_days: int) -> list[dict[str, Any]]:
    return [item for item in items if _within_lookback(item.get("created_at"), lookback_days=lookback_days)]


def _item_title(item: dict[str, Any]) -> str:
    return str(item.get("title") or item.get("text") or "").strip()


def _title_is_negative(title: str, *, keywords: tuple[str, ...]) -> bool:
    text = str(title or "").strip()
    if not text:
        return False
    upper = text.upper()
    for kw in keywords:
        token = str(kw).strip()
        if not token:
            continue
        if token.upper() in upper or token in text:
            return True
    return False


def classify_intel_sentiment(
    intel_row: Optional[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[str, str]:
    """Return (sentiment, headline) where sentiment is positive | negative | neutral."""
    if not intel_row:
        return "neutral", ""
    cfg = _intel_cfg(settings)
    keywords = cfg["negative_keywords"]

    for item in intel_row.get("announcements") or []:
        title = _item_title(item)
        if title and _title_is_negative(title, keywords=keywords):
            return "negative", title

    for item in intel_row.get("news") or []:
        title = _item_title(item)
        if title and _title_is_negative(title, keywords=keywords):
            return "negative_news", title

    if intel_row.get("announcements") or intel_row.get("news"):
        first = intel_row.get("announcements") or intel_row.get("news") or []
        headline = _item_title(first[0]) if first else ""
        return "positive", headline
    return "neutral", ""


def fetch_symbol_intel(
    symbol: str,
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _intel_cfg(settings)
    try:
        from agent_reach.channels import xueqiu as xq_mod

        xq_mod._ensure_cookies()
        ch = xq_mod.XueqiuChannel()
        announcements = _filter_recent(
            ch.get_stock_announcements(symbol, limit=cfg["announcement_limit"]),
            lookback_days=cfg["lookback_days"],
        )
        news = _filter_recent(
            ch.get_stock_news(symbol, limit=cfg["news_limit"]),
            lookback_days=cfg["lookback_days"],
        )
        out = {
            "symbol": symbol,
            "announcements": announcements,
            "news": news,
        }
        sentiment, headline = classify_intel_sentiment(out, settings=settings)
        out["sentiment"] = sentiment
        if headline:
            out["headline"] = headline
        return out
    except Exception as exc:
        logger.warning("watchlist intel fetch failed for {}: {}", symbol, exc)
        return {"symbol": symbol, "announcements": [], "news": [], "error": str(exc)}


def _target_symbols(
    portfolio: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> list[dict[str, str]]:
    from agent_reach.daily_run.snapshot_builder import _normalize_code, code_to_xueqiu_symbol

    cfg = _intel_cfg(settings)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(code: str, name: str) -> None:
        norm = _normalize_code(code)
        if not norm or len(norm) != 6 or norm in seen:
            return
        seen.add(norm)
        rows.append({"code": norm, "name": name or norm, "symbol": code_to_xueqiu_symbol(norm)})

    for item in portfolio.get("watchlist") or []:
        if isinstance(item, dict):
            _add(str(item.get("code") or ""), str(item.get("name") or ""))
        if len(rows) >= cfg["symbol_limit"]:
            return rows

    if cfg["include_candidates"]:
        from agent_reach.daily_run.watchlist_candidates import effective_watchlist_candidates

        for cand in effective_watchlist_candidates(settings or {})[: cfg["candidate_limit"]]:
            if not isinstance(cand, dict):
                continue
            _add(str(cand.get("code") or ""), str(cand.get("name") or ""))
            if len(rows) >= cfg["symbol_limit"]:
                break
    return rows


def collect_watchlist_intel(
    portfolio: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, dict[str, Any]]:
    if not watchlist_intel_enabled(settings):
        return {}

    out: dict[str, dict[str, Any]] = {}
    for row in _target_symbols(portfolio, settings=settings):
        code = row["code"]
        intel = fetch_symbol_intel(row["symbol"], settings=settings)
        intel["code"] = code
        intel["name"] = row["name"]
        if intel.get("announcements") or intel.get("news"):
            out[code] = intel
    return out


def intel_score_adjustment(
    intel_row: Optional[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> float:
    if not intel_row:
        return 0.0
    cfg = _intel_cfg(settings)
    sentiment, _ = classify_intel_sentiment(intel_row, settings=settings)
    if sentiment == "negative":
        return cfg["negative_announcement_penalty"]
    if sentiment == "negative_news":
        return cfg["negative_news_penalty"]
    boost = 0.0
    if intel_row.get("announcements"):
        boost += cfg["announcement_boost"]
    if intel_row.get("news"):
        boost += cfg["news_boost"]
    return boost


def intel_score_boost(intel_row: Optional[dict[str, Any]], *, settings: Optional[dict[str, Any]] = None) -> float:
    """Backward-compatible alias — returns score delta including negative penalties."""
    return intel_score_adjustment(intel_row, settings=settings)


def watchlist_remove_negative_intel_reason(
    code: str,
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    cfg = _intel_cfg(settings)
    if not cfg["negative_intel_remove_enabled"]:
        return None
    from agent_reach.daily_run.snapshot_builder import _normalize_code

    norm = _normalize_code(code)
    intel = (snapshot.get("watchlist_intel") or {}).get(norm)
    if not intel:
        return None
    sentiment, headline = classify_intel_sentiment(intel, settings=settings)
    if sentiment != "negative":
        return None
    title = headline[:32] if headline else "利空公告"
    return f"利空公告：{title}"


def intel_reason_suffix(intel_row: Optional[dict[str, Any]]) -> str:
    if not intel_row:
        return ""
    sentiment = str(intel_row.get("sentiment") or "positive")
    parts: list[str] = []
    for key, label in (("announcements", "公告"), ("news", "资讯")):
        rows = intel_row.get(key) or []
        if not rows:
            continue
        title = _item_title(rows[0])
        if title:
            prefix = "利空" if sentiment.startswith("negative") else label
            parts.append(f"{prefix}：{title[:28]}")
    return f" · {'；'.join(parts)}" if parts else ""


def intel_line_for_code(
    intel_by_code: dict[str, dict[str, Any]],
    code: str,
) -> str:
    intel = intel_by_code.get(code) or {}
    suffix = intel_reason_suffix(intel)
    return suffix.lstrip(" · ") if suffix else ""


def render_watchlist_intel_markdown(
    intel_by_code: dict[str, dict[str, Any]],
    *,
    watchlist: Optional[list[dict[str, Any]]] = None,
    limit: int = 5,
) -> str:
    if not intel_by_code:
        return ""
    codes = []
    if watchlist:
        from agent_reach.daily_run.snapshot_builder import _normalize_code

        codes = [_normalize_code(str(w.get("code") or "")) for w in watchlist if w.get("code")]
    rows = []
    for code, intel in intel_by_code.items():
        if codes and code not in codes:
            continue
        name = intel.get("name") or code
        hint = intel_reason_suffix(intel).lstrip(" · ")
        if hint:
            rows.append(f"- **{name}** ({code}) — {hint}")
        if len(rows) >= limit:
            break
    if not rows:
        return ""
    return "**观察池公告/资讯**\n\n" + "\n".join(rows)


def watchlist_intel_narrative_summary(
    snapshot: Optional[dict[str, Any]] = None,
    *,
    portfolio_summary: Optional[dict[str, Any]] = None,
    limit: int = 2,
) -> str:
    """Compact one-liner for LLM / deterministic narratives."""
    intel_by_code: dict[str, Any] = {}
    if snapshot:
        intel_by_code = dict(snapshot.get("watchlist_intel") or {})
    if not intel_by_code and portfolio_summary:
        intel_by_code = dict(portfolio_summary.get("watchlist_intel") or {})
    if not intel_by_code:
        return ""

    parts: list[str] = []
    for code, intel in intel_by_code.items():
        if not isinstance(intel, dict):
            continue
        name = intel.get("name") or code
        hint = intel_reason_suffix(intel).lstrip(" · ")
        if hint:
            parts.append(f"{name}：{hint}")
        if len(parts) >= limit:
            break
    if not parts:
        return ""
    return "观察池情报：" + "；".join(parts)

# -*- coding: utf-8
"""RedFox sentiment / hot-list collection for daily-run (Path B)."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.hot_news_collector import portfolio_keywords, _matches_keywords
from agent_reach.daily_run.redfox_client import (
    DEFAULT_STOCK_KEYWORDS,
    expand_keywords,
    fetch_gzh_astock,
    fetch_stock_feed,
    fetch_trending_hub,
    fetch_weibo_search,
    get_api_key,
    redfox_enabled,
)
from agent_reach.daily_run.prior_close import prev_trading_day
from agent_reach.daily_run.trade_calendar import today_shanghai

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger("agent_reach.daily_run")

WORKFLOW_ALIASES = {
    "premarket": "morning",
    "morning": "morning",
    "intraday": "intraday",
    "close": "close",
    "verify": "close",
    "weekly": "weekly",
    "forecast": "weekly",
}

BULLISH_WORDS = ("大涨", "涨停", "突破", "利好", "反弹", "强势", "加仓", "看多", "牛市")
BEARISH_WORDS = ("大跌", "跌停", "跳水", "利空", "回调", "弱势", "减仓", "看空", "熊市", "崩盘")


@dataclass
class RedfoxResult:
    stock_feed_items: list[dict[str, Any]] = field(default_factory=list)
    trending_items: list[dict[str, Any]] = field(default_factory=list)
    weibo_items: list[dict[str, Any]] = field(default_factory=list)
    gzh_personal: list[dict[str, Any]] = field(default_factory=list)
    gzh_official: list[dict[str, Any]] = field(default_factory=list)
    matched: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    gzh_summary: str = ""
    cross_validation: str = ""
    platforms_ok: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_feed_items": self.stock_feed_items,
            "trending_items": self.trending_items,
            "weibo_items": self.weibo_items,
            "gzh_personal": self.gzh_personal,
            "gzh_official": self.gzh_official,
            "matched": self.matched,
            "summary": self.summary,
            "gzh_summary": self.gzh_summary,
            "cross_validation": self.cross_validation,
            "platforms_ok": self.platforms_ok,
            "errors": self.errors,
        }


def redfox_cache_dir(settings: Optional[dict[str, Any]] = None) -> Path:
    cfg = (settings or {}).get("redfox") or {}
    raw = str(cfg.get("cache_dir") or "~/.agent-reach/daily_run/cache/redfox")
    return Path(raw).expanduser()


def gzh_subscriptions_path(settings: Optional[dict[str, Any]] = None) -> Path:
    cfg = ((settings or {}).get("redfox") or {}).get("gzh_astock") or {}
    raw = str(cfg.get("subscriptions_file") or "~/.agent-reach/daily_run/redfox/gzh_subscriptions.json")
    return Path(raw).expanduser()


def load_gzh_subscriptions(settings: Optional[dict[str, Any]] = None) -> dict[str, list[str]]:
    path = gzh_subscriptions_path(settings)
    if not path.is_file():
        return {"official": [], "personal": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "official": [str(x) for x in (data.get("official") or [])],
            "personal": [str(x) for x in (data.get("personal") or [])],
        }
    except (json.JSONDecodeError, OSError):
        return {"official": [], "personal": []}


def save_gzh_subscriptions(
    data: dict[str, list[str]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> Path:
    path = gzh_subscriptions_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _filter_gzh_accounts(
    personal: list[dict[str, Any]],
    official: list[dict[str, Any]],
    subscriptions: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    off_names = subscriptions.get("official") or []
    per_names = subscriptions.get("personal") or []
    if not off_names and not per_names:
        return personal, official
    filtered_off = [a for a in official if a.get("account_name") in off_names] if off_names else official
    filtered_per = [a for a in personal if a.get("account_name") in per_names] if per_names else personal
    return filtered_per, filtered_off


def _workflow_name(report_type: str) -> str:
    return WORKFLOW_ALIASES.get(report_type, report_type)


def _sub_enabled(settings: dict[str, Any], section: str, workflow: str) -> bool:
    cfg = settings.get("redfox") or {}
    sub = cfg.get(section) or {}
    if sub.get("enabled") is False:
        return False
    workflows = sub.get("workflows")
    if workflows is None:
        return True
    return workflow in workflows


def _cache_get(path: Path, ttl_seconds: int) -> Optional[dict[str, Any]]:
    if ttl_seconds <= 0:
        return None
    if not path.is_file():
        return None
    try:
        if time.time() - path.stat().st_mtime > ttl_seconds:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _cache_put(path: Path, data: dict[str, Any], *, ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _build_search_keywords(portfolio: dict[str, Any], settings: dict[str, Any]) -> list[str]:
    cfg = settings.get("redfox") or {}
    feed_cfg = cfg.get("stock_feed") or {}
    keys: list[str] = []
    seen: set[str] = set()

    if feed_cfg.get("use_default_keywords", True) is not False:
        for kw in DEFAULT_STOCK_KEYWORDS.split(","):
            kw = kw.strip()
            if kw and kw not in seen:
                seen.add(kw)
                keys.append(kw)

    for kw in portfolio_keywords(portfolio, settings):
        if kw and kw not in seen:
            seen.add(kw)
            keys.append(kw)
    return keys[:20]


def _trending_keywords(portfolio: dict[str, Any], settings: dict[str, Any]) -> list[str]:
    cfg = settings.get("redfox") or {}
    th_cfg = cfg.get("trending_hub") or {}
    expand = th_cfg.get("expand_keywords", True) is not False
    out: list[str] = []
    seen: set[str] = set()
    for kw in portfolio_keywords(portfolio, settings)[:8]:
        terms = expand_keywords(kw) if expand else [kw]
        for term in terms:
            if term and term not in seen:
                seen.add(term)
                out.append(term)
    return out[:15]


def _today_hot_window() -> tuple[str, str]:
    from agent_reach.daily_run.redfox_client import _now_shanghai

    now = _now_shanghai()
    end = now.replace(minute=0, second=0, microsecond=0)
    start = end.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def merge_portfolio_for_redfox(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Merge snapshot portfolio block + watchlist for keyword/cache consistency."""
    from agent_reach.daily_run.snapshot_builder import load_portfolio

    base = load_portfolio()
    block = snapshot.get("portfolio")
    if isinstance(block, dict):
        for key in ("holdings", "cash", "cash_ratio", "total"):
            if block.get(key) is not None:
                base[key] = block[key]
    watchlist = snapshot.get("watchlist")
    if isinstance(watchlist, list) and watchlist:
        merged_rows: list[dict[str, Any]] = []
        for row in watchlist:
            if not isinstance(row, dict):
                continue
            merged_rows.append(
                {
                    "code": row.get("code"),
                    "name": row.get("name"),
                    "keywords": row.get("keywords"),
                }
            )
        if merged_rows:
            base["watchlist"] = merged_rows
    return base


def redfox_result_from_snapshot(snapshot: dict[str, Any]) -> Optional[RedfoxResult]:
    """Reuse RedFox payload already attached during snapshot/macro collection."""
    for key in ("redfox",):
        raw = snapshot.get(key)
        if isinstance(raw, dict) and (raw.get("summary") or raw.get("gzh_summary") or raw.get("matched")):
            return _result_from_dict(raw)
    signals = snapshot.get("macro_signals") or {}
    raw = signals.get("redfox")
    if isinstance(raw, dict):
        return _result_from_dict(raw)
    return None


def _sentiment_titles(redfox: RedfoxResult, *, limit: int = 20) -> list[str]:
    pool = redfox.matched or (redfox.stock_feed_items + redfox.trending_items + redfox.weibo_items)
    return [str(i.get("title") or "") for i in pool[:limit] if i.get("title")]


def _sentiment_score(texts: list[str]) -> float:
    bull = bear = 0
    for text in texts:
        for w in BULLISH_WORDS:
            if w in text:
                bull += 1
        for w in BEARISH_WORDS:
            if w in text:
                bear += 1
    if bull == bear == 0:
        return 0.0
    return float(bull - bear)


def cross_validate_emotion(
    market_review: Optional[dict[str, Any]],
    redfox: RedfoxResult,
) -> str:
    """Compare eastmoney emotion grade with RedFox social sentiment."""
    if not market_review:
        return ""
    titles = _sentiment_titles(redfox)
    if not titles:
        return ""
    em = market_review.get("emotion") or {}
    rating = str(em.get("rating") or "中")
    score = _sentiment_score(titles)
    if score >= 2 and rating == "弱":
        return "RedFox 舆情偏暖，与东财情绪定级「弱」存在分歧，宜交叉验证"
    if score <= -2 and rating == "强":
        return "RedFox 舆情偏冷，与东财情绪定级「强」存在分歧，宜交叉验证"
    if score >= 1 and rating == "强":
        return "RedFox 跨平台舆情与东财「强」情绪一致"
    if score <= -1 and rating == "弱":
        return "RedFox 跨平台舆情与东财「弱」情绪一致"
    return "RedFox 舆情与东财情绪定级大致中性"


def _gzh_query_date(workflow: str, settings: dict[str, Any]) -> str:
    """Morning uses prior trading day (RedFox 07:00 refresh); close uses today."""
    if workflow == "morning":
        return prev_trading_day(settings=settings).isoformat()
    return today_shanghai().isoformat()


def collect_redfox_context(
    portfolio: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    workflow: str = "morning",
) -> RedfoxResult:
    """Collect optional RedFox API enrichment; no-op when disabled or missing key."""
    cfg = settings or {}
    out = RedfoxResult()
    if not redfox_enabled(cfg):
        return out

    wf = _workflow_name(workflow)
    rf_cfg = cfg.get("redfox") or {}
    ttl = int(rf_cfg.get("cache_ttl_seconds", 3600))
    timeout = int(rf_cfg.get("timeout_seconds", 20))
    api_key = get_api_key(cfg)
    keywords = portfolio_keywords(portfolio, cfg)
    cache_key = hashlib.md5(f"{wf}:{','.join(keywords[:5])}".encode()).hexdigest()[:12]
    cache_path = redfox_cache_dir(cfg) / f"{today_shanghai().isoformat()}_{wf}_{cache_key}.json"
    cached = _cache_get(cache_path, ttl)
    if cached:
        return _result_from_dict(cached)

    # --- stock-feed (combined keyword string) ---
    if _sub_enabled(cfg, "stock_feed", wf):
        feed_cfg = rf_cfg.get("stock_feed") or {}
        search_keys = _build_search_keywords(portfolio, cfg)
        keyword_str = ",".join(search_keys[:12]) if search_keys else DEFAULT_STOCK_KEYWORDS
        try:
            feed = fetch_stock_feed(
                keyword_str,
                platforms=list(feed_cfg.get("platforms") or ["xhs", "dy", "gzh"]),
                days=int(feed_cfg.get("days", 7)),
                api_key=api_key,
                timeout=timeout,
                settings=cfg,
            )
            if feed.get("error"):
                out.errors.append(f"stock_feed: {feed['error']}")
            else:
                out.stock_feed_items = feed.get("items") or []
                for plat in feed.get("platforms") or []:
                    if plat not in out.platforms_ok:
                        out.platforms_ok.append(plat)
        except Exception as exc:
            logger.debug("redfox stock_feed failed: {}", exc)
            out.errors.append(f"stock_feed: {exc}")

    # --- trending-hub ---
    if _sub_enabled(cfg, "trending_hub", wf):
        th_cfg = rf_cfg.get("trending_hub") or {}
        try:
            start, end = _today_hot_window()
            trend = fetch_trending_hub(
                source=str(th_cfg.get("source") or "全平台热点事件"),
                platforms=list(th_cfg.get("platforms") or ["wb", "dy", "zh"]),
                keywords=_trending_keywords(portfolio, cfg) or None,
                start_date=start,
                end_date=end,
                api_key=api_key,
                timeout=timeout,
                settings=cfg,
            )
            if trend.get("error"):
                out.errors.append(f"trending_hub: {trend['error']}")
            else:
                out.trending_items = trend.get("items") or []
                for plat in trend.get("platforms") or []:
                    tag = f"trend_{plat}"
                    if tag not in out.platforms_ok:
                        out.platforms_ok.append(tag)
        except Exception as exc:
            logger.debug("redfox trending_hub failed: {}", exc)
            out.errors.append(f"trending_hub: {exc}")

    # --- gzh-astock-top (morning) ---
    if _sub_enabled(cfg, "gzh_astock", wf):
        gzh_cfg = rf_cfg.get("gzh_astock") or {}
        try:
            gzh = fetch_gzh_astock(
                _gzh_query_date(wf, cfg),
                dual_category=gzh_cfg.get("dual_category", True) is not False,
                api_key=api_key,
                timeout=timeout,
                settings=cfg,
            )
            if gzh.get("error"):
                out.errors.append(f"gzh_astock: {gzh['error']}")
            else:
                max_n = int(gzh_cfg.get("max_accounts_per_category", 5))
                personal = (gzh.get("personal") or [])[:max_n]
                official = (gzh.get("official") or [])[:max_n]
                if gzh_cfg.get("use_subscriptions") is not False:
                    subs = load_gzh_subscriptions(cfg)
                    personal, official = _filter_gzh_accounts(personal, official, subs)
                out.gzh_personal = personal
                out.gzh_official = official
                if out.gzh_personal or out.gzh_official:
                    out.platforms_ok.append("gzh_astock")
        except Exception as exc:
            logger.debug("redfox gzh_astock failed: {}", exc)
            out.errors.append(f"gzh_astock: {exc}")

    if _sub_enabled(cfg, "weibo_realtime", wf):
        wb_cfg = rf_cfg.get("weibo_realtime") or {}
        try:
            search_keys = portfolio_keywords(portfolio, cfg)[: int(wb_cfg.get("max_keywords", 2))]
            for kw in search_keys:
                wb = fetch_weibo_search(
                    kw,
                    search_type=str(wb_cfg.get("search_type", "61")),
                    api_key=api_key,
                    timeout=timeout,
                    settings=cfg,
                )
                if wb.get("error"):
                    out.errors.append(f"weibo_search({kw}): {wb['error']}")
                else:
                    out.weibo_items.extend(wb.get("items") or [])
            if out.weibo_items:
                out.platforms_ok.append("weibo_realtime")
        except Exception as exc:
            logger.debug("redfox weibo_realtime failed: {}", exc)
            out.errors.append(f"weibo_realtime: {exc}")

    all_items = out.stock_feed_items + out.trending_items + out.weibo_items
    if keywords:
        out.matched = [
            i for i in all_items if _matches_keywords(str(i.get("title") or ""), keywords)
        ]
    else:
        out.matched = all_items[:10]

    out.summary = _build_summary(out)
    out.gzh_summary = _build_gzh_summary(out)
    _cache_put(cache_path, out.to_dict(), ttl_seconds=ttl)
    return out


def attach_redfox_close_markdown(
    snapshot: dict[str, Any],
    market_review: Optional[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[str, Optional[RedfoxResult]]:
    """Reuse snapshot RedFox data; cross-validate vs market review when available."""
    cfg = settings or {}
    if not redfox_enabled(cfg):
        return "", None

    result = redfox_result_from_snapshot(snapshot)
    if result is None:
        pf = merge_portfolio_for_redfox(snapshot)
        result = collect_redfox_context(pf, settings=cfg, workflow="close")
        snapshot["redfox"] = result.to_dict()

    if market_review:
        result.cross_validation = cross_validate_emotion(market_review, result)

    md = render_redfox_markdown(result)
    return md, result


def _build_summary(result: RedfoxResult) -> str:
    parts: list[str] = []
    if result.matched:
        tops = [
            f"[{i.get('platform')}] {i.get('title', '')[:40]}"
            for i in result.matched[:3]
        ]
        parts.append("RedFox 持仓相关：" + " | ".join(tops))
    elif result.stock_feed_items:
        tops = [
            f"[{i.get('platform')}] {i.get('title', '')[:35]}"
            for i in result.stock_feed_items[:2]
        ]
        parts.append("RedFox 舆情：" + " | ".join(tops))
    if result.trending_items and not result.matched:
        tops = [i.get("title", "")[:35] for i in result.trending_items[:2]]
        parts.append("RedFox 热榜：" + " | ".join(tops))
    return "；".join(parts)[:240]


def _build_gzh_summary(result: RedfoxResult) -> str:
    lines: list[str] = []
    for acc in result.gzh_official[:2]:
        title = acc.get("latest_title")
        if title:
            lines.append(f"官媒·{acc.get('account_name')}：{str(title)[:30]}")
    for acc in result.gzh_personal[:2]:
        title = acc.get("latest_title")
        if title:
            lines.append(f"大V·{acc.get('account_name')}：{str(title)[:30]}")
    return " | ".join(lines)[:240]


def render_redfox_markdown(result: RedfoxResult) -> str:
    if not result.summary and not result.gzh_summary:
        return ""
    lines = ["### 🦊 RedFox 舆情增强", ""]
    if result.gzh_summary:
        lines.append(f"**公众号：** {result.gzh_summary}")
    if result.summary:
        lines.append(f"**跨平台：** {result.summary}")
    if result.cross_validation:
        lines.append(f"**交叉验证：** {result.cross_validation}")
    if result.errors:
        lines.append(f"> API 部分失败：{'; '.join(result.errors[:2])}")
    return "\n".join(lines)


def _result_from_dict(data: dict[str, Any]) -> RedfoxResult:
    return RedfoxResult(
        stock_feed_items=list(data.get("stock_feed_items") or []),
        trending_items=list(data.get("trending_items") or []),
        weibo_items=list(data.get("weibo_items") or []),
        gzh_personal=list(data.get("gzh_personal") or []),
        gzh_official=list(data.get("gzh_official") or []),
        matched=list(data.get("matched") or []),
        summary=str(data.get("summary") or ""),
        gzh_summary=str(data.get("gzh_summary") or ""),
        cross_validation=str(data.get("cross_validation") or ""),
        platforms_ok=list(data.get("platforms_ok") or []),
        errors=list(data.get("errors") or []),
    )

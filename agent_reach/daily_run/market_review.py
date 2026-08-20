# -*- coding: utf-8
"""Daily market review orchestration, persistence, and Feishu rendering."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.lhb_collector import analyze_lhb
from agent_reach.daily_run.market_breadth_collector import analyze_emotion, analyze_emotion_from_counts
from agent_reach.daily_run.sector_mainline import analyze_sectors
from agent_reach.daily_run.trade_calendar import is_trading_day, today_shanghai


def market_review_enabled(settings: dict[str, Any]) -> bool:
    cfg = settings.get("market_review") or {}
    return cfg.get("enabled", True) is not False


def market_review_dir() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "market_review"


def market_review_path(review_date: str) -> Path:
    return market_review_dir() / f"{review_date}.json"


def load_market_review(review_date: str) -> Optional[dict[str, Any]]:
    path = market_review_path(review_date)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_market_review(review: dict[str, Any], review_date: Optional[str] = None) -> Path:
    ds = review_date or review.get("date") or today_shanghai().isoformat()
    review = {**review, "date": ds}
    out = market_review_path(ds)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def list_saved_review_dates(*, limit: int = 60) -> list[str]:
    root = market_review_dir()
    if not root.exists():
        return []
    dates = sorted(
        (p.stem for p in root.glob("*.json") if p.stem[:4].isdigit()),
        reverse=True,
    )
    return dates[:limit]


def compare_market_review(
    current: dict[str, Any],
    *,
    yesterday: Optional[dict[str, Any]] = None,
    last_week: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build vs-yesterday / vs-last-week deltas for key metrics."""
    cur_em = (current.get("emotion") or {})
    out: dict[str, Any] = {"vs_yesterday": None, "vs_last_week": None}

    def _delta(prev: dict[str, Any]) -> dict[str, Any]:
        prev_em = prev.get("emotion") or {}
        return {
            "date": prev.get("date"),
            "limit_up_delta": int(cur_em.get("limit_up") or 0) - int(prev_em.get("limit_up") or 0),
            "limit_down_delta": int(cur_em.get("limit_down") or 0) - int(prev_em.get("limit_down") or 0),
            "up_count_delta": int(cur_em.get("up_count") or 0) - int(prev_em.get("up_count") or 0),
            "down_count_delta": int(cur_em.get("down_count") or 0) - int(prev_em.get("down_count") or 0),
            "emotion_score_delta": int(cur_em.get("score") or 0) - int(prev_em.get("score") or 0),
            "rating_prev": prev_em.get("rating"),
            "rating_current": cur_em.get("rating"),
            "northbound_delta_yi": round(
                float(cur_em.get("northbound_net_yi") or 0)
                - float(prev_em.get("northbound_net_yi") or 0),
                2,
            ),
        }

    if yesterday:
        out["vs_yesterday"] = _delta(yesterday)
    if last_week:
        out["vs_last_week"] = _delta(last_week)
    return out


def _prev_trading_review(
    review_date: date,
    *,
    settings: Optional[dict[str, Any]] = None,
    offset_days: int = 1,
) -> Optional[dict[str, Any]]:
    cursor = review_date - timedelta(days=offset_days)
    cfg = settings or {}
    for _ in range(20):
        ok, _ = is_trading_day(cursor, settings=cfg)
        if ok:
            saved = load_market_review(cursor.isoformat())
            if saved:
                return saved
        cursor -= timedelta(days=1)
    return None


def _macro_breadth_fallback(
    indices: dict[str, Any],
    north: dict[str, Any],
) -> dict[str, Any]:
    """Minimal emotion when full A-share list is unavailable."""
    from agent_reach.daily_run.market_breadth_collector import MarketEmotion

    reasons: list[str] = ["全 A 宽度不可用，仅指数+北向估算"]
    warnings = ["市场宽度降级：缺少涨跌家数/涨跌停统计"]
    score = 0
    sh = indices.get("sh000001") or {}
    pct = sh.get("change_pct")
    if pct is not None:
        pct_f = float(pct)
        reasons.append(f"上证 {pct_f:+.2f}%")
        if pct_f > 1:
            score += 1
        elif pct_f < -1:
            score -= 1

    net = float(north.get("net_yi") or 0)
    if net > 50:
        score += 1
        reasons.append(f"北向大幅流入 {net:.0f} 亿")
    elif net > 0:
        reasons.append(f"北向小幅流入 {net:.0f} 亿")
    elif net < -50:
        score -= 1
        warnings.append(f"北向大幅流出 {abs(net):.0f} 亿")
        reasons.append(f"北向大幅流出 {abs(net):.0f} 亿")
    elif net < 0:
        reasons.append(f"北向小幅流出 {abs(net):.0f} 亿")

    if score >= 4:
        rating, position = "强", "7-8成"
    elif score >= 1:
        rating, position = "中", "5成"
    else:
        rating, position = "弱", "2-3成"

    em = MarketEmotion(
        score=score,
        rating=rating,
        position=position,
        reasons=reasons,
        warnings=warnings,
        northbound_net_yi=net,
    )
    out = em.to_dict()
    out["breadth_degraded"] = True
    return out


def _try_xueqiu_breadth_emotion(
    north: dict[str, Any],
    indices: dict[str, Any],
    *,
    timeout: float,
    enabled: bool = True,
) -> tuple[Optional[dict[str, Any]], list[str], Optional[dict[str, Any]]]:
    """Return (emotion_dict, warnings, breadth_meta) from Xueqiu SH+SZ detail."""
    if not enabled:
        return None, [], None
    try:
        from agent_reach.daily_run.xueqiu_breadth_collector import fetch_xueqiu_market_breadth

        breadth = fetch_xueqiu_market_breadth(timeout=timeout)
        em = analyze_emotion_from_counts(
            int(breadth["up_count"]),
            int(breadth["down_count"]),
            int(breadth["flat_count"]),
            north,
            indices=indices,
            by_market=breadth.get("by_market"),
        )
        out = em.to_dict()
        out["breadth_source"] = "xueqiu"
        out["breadth_partial"] = True
        meta = {
            "up_count": breadth["up_count"],
            "down_count": breadth["down_count"],
            "flat_count": breadth["flat_count"],
            "by_market": breadth.get("by_market"),
        }
        return out, ["市场宽度改用雪球沪+深汇总"], meta
    except Exception as exc:
        return None, [f"xueqiu breadth: {exc}"], None


def collect_market_review(
    *,
    review_date: Optional[str] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Fetch market data with Eastmoney → akshare → xueqiu → macro fallbacks."""
    from agent_reach.daily_run.settings import load_settings

    cfg = settings or load_settings()
    mr_cfg = cfg.get("market_review") or {}
    timeout = float(mr_cfg.get("fetch_timeout_seconds", 15))
    akshare_ttl = int((cfg.get("akshare") or {}).get("spot_ttl", 60))
    ds = review_date or today_shanghai().isoformat()
    day = date.fromisoformat(ds)

    from agent_reach.daily_run import eastmoney_market as em

    warnings: list[str] = []
    source_parts: list[str] = []

    indices, w = em._safe_list(em.fetch_indices, timeout=timeout, label="指数")
    warnings.extend(w)
    if indices:
        source_parts.append("eastmoney_indices")

    stocks, stock_source, stock_warnings = em.fetch_all_stocks_resilient(
        timeout=timeout,
        akshare_ttl=akshare_ttl,
    )
    warnings.extend(stock_warnings)
    if stock_source != "none":
        source_parts.append(stock_source)

    north, north_warnings = em.fetch_north_flow_resilient(timeout=timeout)
    warnings.extend(north_warnings)
    if north.get("source"):
        source_parts.append(str(north["source"]))
    elif north.get("net_yi") is not None:
        source_parts.append("eastmoney_north")

    industries, w = em._safe_list(em.fetch_industry_boards, timeout=timeout, label="行业板块")
    warnings.extend(w)
    concepts, w = em._safe_list(em.fetch_concept_boards, timeout=timeout, label="概念板块")
    warnings.extend(w)
    sector_flow, w = em._safe_list(em.fetch_sector_fund_flow, timeout=timeout, label="板块资金流")
    warnings.extend(w)
    fund_rank, w = em._safe_list(em.fetch_fund_flow_rank, timeout=timeout, label="个股资金流")
    warnings.extend(w)
    lhb_raw = em.fetch_lhb(ds, timeout=timeout)

    if stocks:
        limit_up_stocks = [s for s in stocks if float(s.get("change_pct") or 0) >= 9.8]
        emotion = analyze_emotion(stocks, north, indices=indices).to_dict()
        if stock_source == "akshare":
            emotion.setdefault("warnings", []).append("宽度数据来自 akshare 回退")
        breadth_meta = None
    else:
        limit_up_stocks = []
        xq_enabled = mr_cfg.get("xueqiu_breadth_fallback", True) is not False
        xq_emotion, xq_warns, breadth_meta = _try_xueqiu_breadth_emotion(
            north,
            indices,
            timeout=timeout,
            enabled=xq_enabled,
        )
        warnings.extend(xq_warns)
        if xq_emotion:
            emotion = xq_emotion
            source_parts.append("xueqiu")
        else:
            emotion = _macro_breadth_fallback(indices, north)
            breadth_meta = None

    sector = analyze_sectors(limit_up_stocks, industries=industries, concepts=concepts)
    lhb = analyze_lhb(lhb_raw)

    yesterday = _prev_trading_review(day, settings=cfg, offset_days=1)
    last_week = _prev_trading_review(day, settings=cfg, offset_days=5)

    payload: dict[str, Any] = {
        "date": ds,
        "source": "+".join(source_parts) if source_parts else "degraded",
        "warnings": warnings,
        "indices": indices,
        "emotion": emotion,
        "north": north,
        "industries": industries[:15],
        "concepts": concepts[:15],
        "sector_flow": sector_flow[:15],
        "fund_rank": fund_rank[:15],
        "limit_up_stocks": limit_up_stocks[:30],
        "sector_analysis": sector.to_dict(),
        "lhb_raw": lhb_raw[:30],
        "lhb_analysis": lhb.to_dict(),
    }
    if breadth_meta:
        payload["breadth_meta"] = breadth_meta
    has_counts = int((emotion or {}).get("up_count") or 0) + int((emotion or {}).get("down_count") or 0) > 0
    if not stocks and not has_counts and not indices:
        payload["error"] = "市场宽度与指数均不可用"
    payload["comparison"] = compare_market_review(
        payload, yesterday=yesterday, last_week=last_week
    )
    return payload


def get_or_collect_market_review(
    *,
    settings: Optional[dict[str, Any]] = None,
    review_date: Optional[str] = None,
    force: bool = False,
) -> Optional[dict[str, Any]]:
    """Load cached daily review or fetch once (dedup per trading day)."""
    from agent_reach.daily_run.settings import load_settings

    cfg = settings or load_settings()
    if not market_review_enabled(cfg):
        return None

    ds = review_date or today_shanghai().isoformat()
    if not force:
        cached = load_market_review(ds)
        if cached:
            return cached

    try:
        review = collect_market_review(review_date=ds, settings=cfg)
    except Exception as exc:
        review = {
            "date": ds,
            "error": str(exc),
            "emotion": _macro_breadth_fallback({}, {"net_yi": 0}),
            "sector_analysis": analyze_sectors([]).to_dict(),
            "lhb_analysis": analyze_lhb([]).to_dict(),
            "warnings": [str(exc)],
        }

    mr_cfg = cfg.get("market_review") or {}
    if mr_cfg.get("persist", True) is not False and "error" not in review:
        save_market_review(review, ds)
    return review


def render_market_review_markdown(review: dict[str, Any]) -> str:
    """Four-card markdown for Feishu close push."""
    if not review:
        return "## 🌡️ 全市场复盘\n\n> 市场宽度数据拉取失败：无数据"

    em = review.get("emotion") or {}
    degraded = em.get("breadth_degraded") is True
    partial = em.get("breadth_partial") is True
    has_breadth = (
        int(em.get("up_count") or 0) + int(em.get("down_count") or 0) > 0 and not degraded
    )

    if review.get("error") and not has_breadth and not review.get("indices"):
        err = review.get("error", "未知错误")
        return f"## 🌡️ 全市场复盘\n\n> 市场宽度数据拉取失败：{err}"

    sa = review.get("sector_analysis") or {}
    la = review.get("lhb_analysis") or {}
    cmp_ = review.get("comparison") or {}
    indices = review.get("indices") or {}
    warnings = list(review.get("warnings") or []) + list(em.get("warnings") or [])

    rating = em.get("rating", "中")
    badge = {"强": "强势 🔥", "中": "中性 ⚖️", "弱": "弱势 ❄️"}.get(rating, rating)
    lines = [
        "## 🌡️ 全市场复盘（a-stock-review）",
        "",
        f"**情绪定级：** {badge} · 综合 **{em.get('score', '—')} 分** · 建议仓位 **{em.get('position', '—')}**",
        "",
    ]

    for w in warnings[:4]:
        lines.append(f"- ⚠️ {w}")

    for r in em.get("reasons") or []:
        lines.append(f"- {r}")

    if indices:
        lines.extend(["", "### 📐 核心指数"])
        for info in indices.values():
            name = info.get("name", "")
            pct = info.get("change_pct")
            pct_s = f"{float(pct):+.2f}%" if pct is not None else "—"
            lines.append(f"- **{name}** {info.get('price', '—')} ({pct_s})")

    lines.extend(["", "### 📊 市场宽度"])
    if has_breadth:
        flat_note = f" / 平 **{em.get('flat_count', '—')}**" if em.get("flat_count") else ""
        lines.extend(
            [
                f"- 上涨 **{em.get('up_count', '—')}** / 下跌 **{em.get('down_count', '—')}**{flat_note} · 涨跌比 **{em.get('ratio', '—')}**",
            ]
        )
        if partial:
            lines.append("- 涨停/跌停/炸板率 **不可用**（雪球宽度无此项）")
        else:
            lines.append(
                f"- 涨停 **{em.get('limit_up', '—')}** / 跌停 **{em.get('limit_down', '—')}** · 炸板率 **{float(em.get('broken_rate') or 0) * 100:.1f}%**"
            )
    else:
        lines.append("- 涨跌家数/涨跌停 **不可用**（已降级为指数+北向估算）")
    lines.append(f"- 北向 **{em.get('northbound_net_yi', '—')} 亿**")

    lines.extend(
        [
            "",
            "## 🔥 板块主线",
            f"**{sa.get('mainline_type', '—')}** — {sa.get('reasoning', '')}",
        ]
    )

    for sec in (sa.get("main_sectors") or [])[:5]:
        tops = "、".join(
            f"{t.get('name')}({t.get('code')})" for t in (sec.get("top_stocks") or [])[:3]
        )
        lines.append(f"- **{sec.get('name')}** 涨停 {sec.get('limit_up_count')} 家 · {tops or '—'}")

    ladder = sa.get("ladder") or []
    if ladder:
        lines.append("")
        lines.append("**连板梯队（估算）：**")
        for rung in ladder[:5]:
            names = "、".join(rung.get("stocks") or [])
            lines.append(f"- {rung.get('board')}板+ · {rung.get('count')} 家 · {names}")

    lines.extend(["", "## 🐉 龙虎榜 & 资金"])
    if la.get("capital_preference"):
        lines.append(la["capital_preference"])
    buyers = la.get("buyers") or []
    if buyers:
        lines.append("")
        lines.append("**净买入 Top：**")
        for s in buyers[:5]:
            lines.append(
                f"- {s.get('name')}({s.get('code')}) 净买 **{float(s.get('net_buy') or 0):.2f}亿**"
            )

    vs_y = cmp_.get("vs_yesterday")
    vs_w = cmp_.get("vs_last_week")
    if vs_y or vs_w:
        lines.extend(["", "## 📈 历史对比"])
        if vs_y:
            lines.append(
                f"- **vs 昨日：** 涨停 {vs_y.get('limit_up_delta', 0):+d} · "
                f"情绪分 {vs_y.get('emotion_score_delta', 0):+d} · "
                f"北向 {vs_y.get('northbound_delta_yi', 0):+.1f}亿 · "
                f"{vs_y.get('rating_prev')}→{vs_y.get('rating_current')}"
            )
        if vs_w:
            lines.append(
                f"- **vs 上周：** 涨停 {vs_w.get('limit_up_delta', 0):+d} · "
                f"情绪分 {vs_w.get('emotion_score_delta', 0):+d} · "
                f"北向 {vs_w.get('northbound_delta_yi', 0):+.1f}亿"
            )

    return "\n".join(lines)

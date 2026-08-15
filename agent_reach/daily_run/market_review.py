# -*- coding: utf-8
"""Daily market review orchestration, persistence, and Feishu rendering."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.lhb_collector import analyze_lhb
from agent_reach.daily_run.market_breadth_collector import analyze_emotion
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


def collect_market_review(
    *,
    review_date: Optional[str] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Fetch Eastmoney data and build full market review payload."""
    from agent_reach.daily_run.settings import load_settings

    cfg = settings or load_settings()
    mr_cfg = cfg.get("market_review") or {}
    timeout = float(mr_cfg.get("fetch_timeout_seconds", 15))
    ds = review_date or today_shanghai().isoformat()
    day = date.fromisoformat(ds)

    from agent_reach.daily_run import eastmoney_market as em

    indices = em.fetch_indices(timeout=timeout)
    stocks = em.fetch_all_stocks(timeout=timeout)
    north = em.fetch_north_flow(timeout=timeout)
    industries = em.fetch_industry_boards(timeout=timeout)
    concepts = em.fetch_concept_boards(timeout=timeout)
    sector_flow = em.fetch_sector_fund_flow(timeout=timeout)
    fund_rank = em.fetch_fund_flow_rank(timeout=timeout)
    lhb_raw = em.fetch_lhb(ds, timeout=timeout)

    limit_up_stocks = [s for s in stocks if float(s.get("change_pct") or 0) >= 9.8]
    emotion = analyze_emotion(stocks, north, indices=indices)
    sector = analyze_sectors(limit_up_stocks, industries=industries, concepts=concepts)
    lhb = analyze_lhb(lhb_raw)

    yesterday = _prev_trading_review(day, settings=cfg, offset_days=1)
    last_week = _prev_trading_review(day, settings=cfg, offset_days=5)

    payload: dict[str, Any] = {
        "date": ds,
        "source": "eastmoney",
        "indices": indices,
        "emotion": emotion.to_dict(),
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
            "emotion": analyze_emotion([], {"net_yi": 0}).to_dict(),
            "sector_analysis": analyze_sectors([]).to_dict(),
            "lhb_analysis": analyze_lhb([]).to_dict(),
        }

    if mr_cfg := cfg.get("market_review") or {}:
        if mr_cfg.get("persist", True) is not False and "error" not in review:
            save_market_review(review, ds)
    return review


def render_market_review_markdown(review: dict[str, Any]) -> str:
    """Four-card markdown for Feishu close push."""
    if not review or review.get("error"):
        err = review.get("error", "未知错误") if review else "无数据"
        return f"## 🌡️ 全市场复盘\n\n> 市场宽度数据拉取失败：{err}"

    em = review.get("emotion") or {}
    sa = review.get("sector_analysis") or {}
    la = review.get("lhb_analysis") or {}
    cmp_ = review.get("comparison") or {}
    indices = review.get("indices") or {}

    rating = em.get("rating", "中")
    badge = {"强": "强势 🔥", "中": "中性 ⚖️", "弱": "弱势 ❄️"}.get(rating, rating)
    lines = [
        "## 🌡️ 全市场复盘（a-stock-review）",
        "",
        f"**情绪定级：** {badge} · 综合 **{em.get('score', '—')} 分** · 建议仓位 **{em.get('position', '—')}**",
        "",
    ]

    for r in em.get("reasons") or []:
        lines.append(f"- {r}")
    for w in em.get("warnings") or []:
        lines.append(f"- ⚠️ {w}")

    if indices:
        lines.extend(["", "### 📐 核心指数"])
        for info in indices.values():
            name = info.get("name", "")
            pct = info.get("change_pct")
            pct_s = f"{float(pct):+.2f}%" if pct is not None else "—"
            lines.append(f"- **{name}** {info.get('price', '—')} ({pct_s})")

    lines.extend(
        [
            "",
            "### 📊 市场宽度",
            f"- 上涨 **{em.get('up_count', '—')}** / 下跌 **{em.get('down_count', '—')}** · 涨跌比 **{em.get('ratio', '—')}**",
            f"- 涨停 **{em.get('limit_up', '—')}** / 跌停 **{em.get('limit_down', '—')}** · 炸板率 **{float(em.get('broken_rate') or 0) * 100:.1f}%**",
            f"- 北向 **{em.get('northbound_net_yi', '—')} 亿**",
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

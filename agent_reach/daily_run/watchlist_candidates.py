# -*- coding: utf-8
"""Weekly hot-sector driven watchlist candidate pool."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.snapshot_builder import _normalize_code
from agent_reach.daily_run.trade_calendar import today_shanghai


def watchlist_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return settings.get("watchlist") or {}


def weekly_candidates_path() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "watchlist_candidates_weekly.json"


@dataclass
class WeeklyCandidateUpdate:
    week_end: str
    sectors: list[str] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_end": self.week_end,
            "sectors": self.sectors,
            "candidates": self.candidates,
            "message": self.message,
            "updated_at": today_shanghai().isoformat(),
        }


def load_weekly_candidates() -> Optional[dict[str, Any]]:
    path = weekly_candidates_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_weekly_candidates(record: dict[str, Any]) -> Path:
    path = weekly_candidates_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _candidate_dict(
    row: dict[str, Any],
    *,
    reason: str,
    source: str = "weekly",
) -> dict[str, Any]:
    code = _normalize_code(str(row.get("code", "")))
    out = dict(row)
    out["code"] = code
    out["reason"] = reason
    out["source"] = source
    return out


def _match_pool_key(sector: str, pools: dict[str, Any]) -> Optional[str]:
    sector = str(sector or "").strip()
    if not sector:
        return None
    if sector in pools:
        return sector
    for key in pools:
        if key in sector or sector in key:
            return key
    return None


def _weekly_candidate_limits(wl_cfg: dict[str, Any]) -> tuple[int, int, int]:
    """Return (sector_limit, min_candidates, max_candidates); sector cap is 10."""
    sector_limit = min(int(wl_cfg.get("weekly_hot_sector_limit", 10)), 10)
    min_candidates = int(wl_cfg.get("weekly_candidates_min", 5))
    max_candidates = int(wl_cfg.get("weekly_candidates_max", 10))
    if max_candidates < min_candidates:
        max_candidates = min_candidates
    return sector_limit, min_candidates, max_candidates


def _rank_hot_sectors(report: dict[str, Any] | Any) -> list[tuple[str, float, str]]:
    data = report.to_dict() if hasattr(report, "to_dict") else report
    scores: dict[str, tuple[float, str]] = {}

    sector_groups = data.get("sector_groups") or {}
    for sector, symbols in sector_groups.items():
        if not symbols or sector in ("综合", "未分类"):
            continue
        changes = [float(s.get("change_pct") or 0) for s in symbols if s.get("change_pct") is not None]
        if not changes:
            continue
        avg = sum(changes) / len(changes)
        scores[str(sector)] = (avg, f"板块均涨 {avg:+.1f}%（{len(symbols)} 只）")

    for item in data.get("hot_sectors") or []:
        sector = str(item.get("sector") or "综合")
        if sector in ("综合", "未分类"):
            from agent_reach.daily_run.sector_classifier import lookup_sector

            sector = lookup_sector(
                str(item.get("code") or ""),
                str(item.get("name") or ""),
            )
        if sector in ("综合", "未分类"):
            continue
        chg = float(item.get("change_pct") or 0)
        name = item.get("name") or item.get("code") or "?"
        prev = scores.get(sector)
        if prev is None or chg > prev[0]:
            scores[sector] = (chg, f"强势 {name} {chg:+.1f}%")

    for row in data.get("sector_research") or []:
        label = str(row.get("label") or row.get("sector") or "").replace(" 板块", "").strip()
        if label and label not in scores:
            scores[label] = (0.5, "本周 Exa 板块调研")

    ranked = sorted(scores.items(), key=lambda kv: kv[1][0], reverse=True)
    return [(name, score, reason) for name, (score, reason) in ranked]


def _add_xueqiu_hot_candidates(
    chosen: list[dict[str, Any]],
    chosen_codes: set[str],
    skip_codes: set[str],
    *,
    macro_signals: dict[str, Any],
    max_candidates: int,
    sector_names: list[str],
) -> None:
    from agent_reach.daily_run.xueqiu_hot_display import normalize_xueqiu_symbol

    boards: list[dict[str, Any]] = []
    for stock in macro_signals.get("hot_stocks") or []:
        if isinstance(stock, dict):
            boards.append({**stock, "board": stock.get("board") or "人气榜"})
    for stock in macro_signals.get("hot_watch_stocks") or []:
        if isinstance(stock, dict):
            boards.append({**stock, "board": stock.get("board") or "关注榜"})
    if not boards:
        return

    for stock in boards:
        if len(chosen) >= max_candidates:
            return
        code = normalize_xueqiu_symbol(str(stock.get("symbol") or ""))
        if not code or len(code) != 6 or code in skip_codes or code in chosen_codes:
            continue
        name = str(stock.get("name") or code)
        board = str(stock.get("board") or "热股")
        rank = stock.get("rank")
        rank_s = f" #{rank}" if rank is not None else ""
        pct = stock.get("percent")
        pct_s = f" {float(pct):+.1f}%" if pct is not None else ""
        chosen.append(
            _candidate_dict(
                {"code": code, "name": name, "keywords": [name[:4], code]},
                reason=f"雪球{board}候选：{name}{rank_s}{pct_s}",
                source="xueqiu_hot",
            )
        )
        chosen_codes.add(code)
        if "雪球热股" not in sector_names:
            sector_names.append("雪球热股")


def _add_eastmoney_screen_candidates(
    chosen: list[dict[str, Any]],
    chosen_codes: set[str],
    skip_codes: set[str],
    *,
    sector_keywords: list[str],
    settings: dict[str, Any],
    max_candidates: int,
    sector_names: list[str],
) -> None:
    wl_cfg = watchlist_settings(settings)
    if wl_cfg.get("eastmoney_screen_candidates_enabled", True) is False:
        return
    plugins = (settings or {}).get("plugins") or {}
    if plugins.get("eastmoney_intent_enabled") is False:
        return

    from agent_reach.daily_run.eastmoney_intent import screen_eastmoney_stocks

    per_sector = int(wl_cfg.get("eastmoney_screen_per_sector", 2))
    skip_labels = {"综合", "未分类", "雪球热股", "热点搜股", "东财选股"}
    for keyword in sector_keywords:
        if len(chosen) >= max_candidates:
            return
        kw = str(keyword or "").strip()
        if not kw or kw in skip_labels:
            continue
        rows = screen_eastmoney_stocks(keyword=kw, settings=settings)
        added = 0
        for row in rows:
            if len(chosen) >= max_candidates or added >= per_sector:
                break
            code = _normalize_code(str(row.get("code") or ""))
            if not code or code in skip_codes or code in chosen_codes:
                continue
            name = str(row.get("name") or code)
            chg = row.get("change_pct")
            chg_s = f" {float(chg):+.1f}%" if chg is not None else ""
            chosen.append(
                _candidate_dict(
                    {"code": code, "name": name, "keywords": [name[:4], kw, code]},
                    reason=f"东财选股：{kw} → {name}{chg_s}",
                    source="eastmoney_screen",
                )
            )
            chosen_codes.add(code)
            added += 1
        if added and "东财选股" not in sector_names:
            sector_names.append("东财选股")


def _add_xueqiu_search_candidates(
    chosen: list[dict[str, Any]],
    chosen_codes: set[str],
    skip_codes: set[str],
    *,
    macro_signals: dict[str, Any],
    max_candidates: int,
    sector_names: list[str],
) -> None:
    rows = macro_signals.get("xueqiu_stock_search") or []
    for row in rows:
        if len(chosen) >= max_candidates:
            return
        if not isinstance(row, dict):
            continue
        code = _normalize_code(str(row.get("code") or ""))
        if not code or code in skip_codes or code in chosen_codes:
            continue
        name = str(row.get("name") or code)
        query = str(row.get("query") or "热点")
        chosen.append(
            _candidate_dict(
                {"code": code, "name": name, "keywords": [name[:4], query, code]},
                reason=f"热点搜股：「{query}」→ {name}",
                source="xueqiu_search",
            )
        )
        chosen_codes.add(code)
        if "热点搜股" not in sector_names:
            sector_names.append("热点搜股")


def build_weekly_watchlist_candidates(
    report: dict[str, Any] | Any,
    settings: dict[str, Any],
) -> WeeklyCandidateUpdate:
    wl_cfg = watchlist_settings(settings)
    if wl_cfg.get("weekly_candidates_enabled", True) is False:
        return WeeklyCandidateUpdate(week_end="", message="weekly_candidates 未启用")

    data = report.to_dict() if hasattr(report, "to_dict") else report
    week_end = str(data.get("week_end") or today_shanghai().isoformat())
    pools = dict(wl_cfg.get("sector_pools") or {})
    sector_limit, min_candidates, max_candidates = _weekly_candidate_limits(wl_cfg)

    static_codes = {
        _normalize_code(str(c.get("code", "")))
        for c in (wl_cfg.get("candidates") or [])
        if c.get("code")
    }
    held_codes = {
        _normalize_code(str(h.get("code", "")))
        for h in (data.get("holdings") or [])
        if h.get("code")
    }
    skip_codes = static_codes | held_codes

    ranked_sectors: list[tuple[str, float, str]] = []
    all_ranked_sectors = _rank_hot_sectors(data)
    for sector, score, sector_reason in all_ranked_sectors:
        if _match_pool_key(sector, pools):
            ranked_sectors.append((sector, score, sector_reason))
        if len(ranked_sectors) >= sector_limit:
            break

    chosen: list[dict[str, Any]] = []
    chosen_codes: set[str] = set()
    sector_names: list[str] = []

    def _add_from_pool(sector: str, sector_reason: str, pool_rows: list[dict[str, Any]]) -> None:
        if sector not in sector_names:
            sector_names.append(sector)
        for row in pool_rows:
            if len(chosen) >= max_candidates:
                return
            code = _normalize_code(str(row.get("code", "")))
            if not code or code in skip_codes or code in chosen_codes:
                continue
            reason = f"本周热点板块：{sector}（{sector_reason}）"
            chosen.append(_candidate_dict(row, reason=reason))
            chosen_codes.add(code)

    for sector, _score, sector_reason in ranked_sectors:
        pool_key = _match_pool_key(sector, pools)
        _add_from_pool(sector, sector_reason, list(pools.get(pool_key or "", []) or []))
        if len(chosen) >= max_candidates:
            break

    macro = dict(data.get("macro_signals") or {})
    if wl_cfg.get("xueqiu_hot_candidates_enabled", True) is not False:
        _add_xueqiu_hot_candidates(
            chosen,
            chosen_codes,
            skip_codes,
            macro_signals=macro,
            max_candidates=max_candidates,
            sector_names=sector_names,
        )
    if wl_cfg.get("xueqiu_search_candidates_enabled", True) is not False:
        _add_xueqiu_search_candidates(
            chosen,
            chosen_codes,
            skip_codes,
            macro_signals=macro,
            max_candidates=max_candidates,
            sector_names=sector_names,
        )

    screen_keywords = list(sector_names)
    if not screen_keywords:
        screen_keywords = [name for name, _, _ in all_ranked_sectors[:5]]
    _add_eastmoney_screen_candidates(
        chosen,
        chosen_codes,
        skip_codes,
        sector_keywords=screen_keywords,
        settings=settings,
        max_candidates=max_candidates,
        sector_names=sector_names,
    )

    if len(chosen) < min_candidates:
        for item in data.get("hot_sectors") or []:
            if len(chosen) >= max_candidates:
                break
            code = _normalize_code(str(item.get("code", "")))
            if not code or code in skip_codes or code in chosen_codes:
                continue
            sector = str(item.get("sector") or "热点")
            chg = item.get("change_pct")
            chg_s = f" {float(chg):+.1f}%" if chg is not None else ""
            name = item.get("name") or code
            chosen.append(
                _candidate_dict(
                    {
                        "code": code,
                        "name": name,
                        "keywords": item.get("keywords") or [name, sector],
                    },
                    reason=f"本周强势标的：{name}{chg_s}（{sector}）",
                )
            )
            chosen_codes.add(code)
            if sector not in sector_names:
                sector_names.append(sector)

    if not chosen:
        msg = "本周无新增板块候选（热点未匹配 sector_pools 或候选已满）"
    elif len(chosen) < min_candidates:
        msg = (
            f"本周热点板块 {', '.join(sector_names)} → 候选 {len(chosen)} 只"
            f"（未达下限 {min_candidates}）"
        )
    else:
        msg = (
            f"本周热点板块 {', '.join(sector_names)} → 新增候选 {len(chosen)} 只"
            f"（按热度顺序，≥{min_candidates}）"
        )

    return WeeklyCandidateUpdate(
        week_end=week_end[:10],
        sectors=sector_names,
        candidates=chosen,
        message=msg,
    )


def update_candidates_from_weekly(
    report: dict[str, Any] | Any,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Persist weekly hot-sector candidates for watchlist fill at morning/close."""
    update = build_weekly_watchlist_candidates(report, settings)
    if not update.candidates and update.message.startswith("weekly"):
        return update.to_dict()
    record = update.to_dict()
    save_weekly_candidates(record)
    return record


def effective_watchlist_candidates(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Static config candidates + latest weekly hot-sector additions."""
    wl_cfg = watchlist_settings(settings)
    static = [dict(c) for c in (wl_cfg.get("candidates") or [])]
    if wl_cfg.get("weekly_candidates_enabled", True) is False:
        return static

    weekly = load_weekly_candidates()
    if not weekly:
        return static

    seen = {_normalize_code(str(c.get("code", ""))) for c in static if c.get("code")}
    merged = list(static)
    for row in weekly.get("candidates") or []:
        code = _normalize_code(str(row.get("code", "")))
        if not code or code in seen:
            continue
        merged.append(dict(row))
        seen.add(code)
    return merged


def render_weekly_candidates_markdown(record: dict[str, Any]) -> str:
    if not record.get("candidates"):
        return f"**观察池候选：** {record.get('message') or '无更新'}"
    lines = [f"**观察池候选更新：** {record.get('message')}"]
    for c in record.get("candidates") or []:
        lines.append(f"- **{c.get('name')}** ({c.get('code')}) — {c.get('reason')}")
    return "\n".join(lines)

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
    max_add = int(wl_cfg.get("weekly_candidates_max", 6))
    sector_limit = int(wl_cfg.get("weekly_hot_sector_limit", 3))
    per_sector = max(1, max_add // max(sector_limit, 1))

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

    ranked_sectors = _rank_hot_sectors(data)[:sector_limit]
    chosen: list[dict[str, Any]] = []
    chosen_codes: set[str] = set()
    sector_names: list[str] = []

    for sector, _score, sector_reason in ranked_sectors:
        sector_names.append(sector)
        pool_key = _match_pool_key(sector, pools)
        pool_rows = list(pools.get(pool_key or "", []) or [])
        added = 0
        for row in pool_rows:
            if len(chosen) >= max_add:
                break
            code = _normalize_code(str(row.get("code", "")))
            if not code or code in skip_codes or code in chosen_codes:
                continue
            reason = f"本周热点板块：{sector}（{sector_reason}）"
            chosen.append(_candidate_dict(row, reason=reason))
            chosen_codes.add(code)
            added += 1
            if added >= per_sector:
                break

        if len(chosen) >= max_add:
            break

    if len(chosen) < max_add:
        for item in data.get("hot_sectors") or []:
            if len(chosen) >= max_add:
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
    else:
        msg = f"本周热点板块 {', '.join(sector_names[:sector_limit])} → 新增候选 {len(chosen)} 只"

    return WeeklyCandidateUpdate(
        week_end=week_end[:10],
        sectors=sector_names[:sector_limit],
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

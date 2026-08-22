# -*- coding: utf-8
"""Persist Saturday weekly digest for Sunday forecast reuse."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.trade_calendar import today_shanghai


def digest_path() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "weekly_digest.json"


def save_weekly_digest(report: dict[str, Any], *, week_end: Optional[str] = None) -> Path:
    path = digest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    macro_signals = dict(report.get("macro_signals") or {})
    record = {
        "saved_at": today_shanghai().isoformat(),
        "week_end": week_end or report.get("week_end"),
        "hot_sectors": report.get("hot_sectors") or [],
        "sector_research": report.get("sector_research") or [],
        "sector_groups": report.get("sector_groups") or {},
        "news_events": report.get("news_events") or [],
        "skill_learning": report.get("skill_learning") or [],
        "macro_signals": macro_signals,
        "watchlist_intel": report.get("watchlist_intel") or {},
        "xueqiu_exa_research": macro_signals.get("xueqiu_exa_research") or [],
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_weekly_digest(max_age_days: int = 2) -> Optional[dict[str, Any]]:
    path = digest_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    saved = data.get("saved_at")
    if saved:
        from datetime import date, timedelta

        try:
            if date.fromisoformat(str(saved)[:10]) < today_shanghai() - timedelta(days=max_age_days):
                return None
        except ValueError:
            pass
    return data

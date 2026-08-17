# -*- coding: utf-8
"""A-share trading calendar — skip cron on holidays/weekends."""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

_SH_TZ = ZoneInfo("Asia/Shanghai")
_CACHE: dict[str, Any] = {"dates": set(), "ts": 0.0, "ttl": 86400}


def today_shanghai() -> date:
    return datetime.now(_SH_TZ).date()


def is_weekend(d: Optional[date] = None) -> bool:
    d = d or today_shanghai()
    return d.weekday() >= 5


def load_holiday_overrides(path: Optional[Path] = None) -> set[str]:
    """Optional JSON: { "holidays": ["2026-01-01"], "workdays": ["2026-02-14"] }"""
    p = path or (Path.home() / ".agent-reach" / "daily_run" / "holidays.json")
    if not p.exists():
        example = Path(__file__).resolve().parents[2] / "config" / "daily_run_holidays.example.json"
        if example.exists():
            p = example
        else:
            return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(str(x) for x in (data.get("holidays") or []))
    except (json.JSONDecodeError, OSError):
        return set()


def load_workday_overrides(path: Optional[Path] = None) -> set[str]:
    p = path or (Path.home() / ".agent-reach" / "daily_run" / "holidays.json")
    if not p.exists():
        example = Path(__file__).resolve().parents[2] / "config" / "daily_run_holidays.example.json"
        if example.exists():
            p = example
        else:
            return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(str(x) for x in (data.get("workdays") or []))
    except (json.JSONDecodeError, OSError):
        return set()


def _load_trade_dates_akshare() -> set[str]:
    now = time.time()
    if _CACHE["dates"] and now - float(_CACHE["ts"]) < float(_CACHE["ttl"]):
        return _CACHE["dates"]

    try:
        from agent_reach.daily_run.akshare_adapter import _import_akshare

        ak = _import_akshare()
        df = ak.tool_trade_date_hist_sina()
        col = "trade_date" if "trade_date" in df.columns else df.columns[0]
        dates = set(str(x)[:10] for x in df[col].tolist())
        _CACHE["dates"] = dates
        _CACHE["ts"] = now
        return dates
    except Exception:
        return set()


def is_trading_day(d: Optional[date] = None, *, settings: Optional[dict] = None) -> tuple[bool, str]:
    """
    Return (is_trading, reason).

    Uses: workday override > trade calendar > holiday override > weekday.
    """
    d = d or today_shanghai()
    ds = d.isoformat()
    cfg = (settings or {}).get("trade_calendar", {})

    if not cfg.get("enabled", True):
        return True, "calendar_disabled"

    if ds in load_workday_overrides():
        return True, "workday_override"

    trade_dates = _load_trade_dates_akshare()
    if trade_dates:
        if ds in trade_dates:
            return True, "akshare_calendar"
        return False, "非交易日（AKShare 日历）"

    if ds in load_holiday_overrides():
        return False, "holiday_override"

    if is_weekend(d):
        return False, "周末"

    return True, "weekday_default"


def trading_days_held(
    acquired: date,
    as_of: Optional[date] = None,
    *,
    settings: Optional[dict] = None,
) -> int:
    """
    Trading days elapsed since acquisition for T+1 sell rules.

    Buy on ``acquired`` -> 0 on that day, 1 on the next trading day, etc.
    """
    end = as_of or today_shanghai()
    if end <= acquired:
        return 0

    trade_dates = _load_trade_dates_akshare()
    if trade_dates:
        start_s = acquired.isoformat()
        end_s = end.isoformat()
        return sum(1 for ds in trade_dates if start_s < ds <= end_s)

    from datetime import timedelta

    count = 0
    d = acquired + timedelta(days=1)
    while d <= end:
        ok, _ = is_trading_day(d, settings=settings)
        if ok:
            count += 1
        d += timedelta(days=1)
    return count

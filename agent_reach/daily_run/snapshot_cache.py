# -*- coding: utf-8
"""Daily snapshot layer cache — macro/technicals reused across intraday scans."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.trade_calendar import today_shanghai

_CACHE_IO_LOCK = __import__("threading").Lock()


def cache_dir() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "cache"


def daily_cache_path(d: Optional[Any] = None) -> Path:
    day = d.isoformat() if d is not None and hasattr(d, "isoformat") else today_shanghai().isoformat()
    return cache_dir() / f"{day}.json"


def load_daily_cache(d: Optional[Any] = None) -> dict[str, Any]:
    path = daily_cache_path(d)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


_TECHNICAL_FIELDS = ("ma20", "ma5", "position_20d", "volume_ratio")


def merge_technicals(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    """Merge per-symbol technical fields; never wipe prior values with empty updates."""
    merged = {code: dict(fields) for code, fields in existing.items() if isinstance(fields, dict)}
    for code, fields in incoming.items():
        if not isinstance(fields, dict):
            continue
        patch = {k: v for k, v in fields.items() if k in _TECHNICAL_FIELDS and v is not None}
        if not patch:
            continue
        prev = merged.get(code)
        if isinstance(prev, dict):
            merged[code] = {**prev, **patch}
        else:
            merged[code] = patch
    return merged


def save_daily_cache(data: dict[str, Any], d: Optional[Any] = None) -> Path:
    with _CACHE_IO_LOCK:
        cache_dir().mkdir(parents=True, exist_ok=True)
        path = daily_cache_path(d)
        existing = load_daily_cache(d)
        payload = dict(data)
        incoming_technicals = payload.pop("technicals", None)
        if isinstance(incoming_technicals, dict):
            existing["technicals"] = merge_technicals(
                existing.get("technicals") or {},
                incoming_technicals,
            )
        existing.update(payload)
        path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path


def last_snapshot_path() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "last_snapshot.json"


def load_last_snapshot() -> Optional[dict[str, Any]]:
    path = last_snapshot_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

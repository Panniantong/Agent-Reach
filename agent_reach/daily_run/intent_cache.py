# -*- coding: utf-8
"""TTL cache + rate limiting for high-intent Eastmoney routing."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from collections.abc import Callable
from typing import Any, Optional

_RATE_FILE = "rate_window.json"


def intent_cache_dir() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "intent_cache"


def intent_config(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = (settings or {}).get("intent") or {}
    return {
        "enabled": cfg.get("enabled", True) is not False,
        "ttl_seconds": int(cfg.get("ttl_seconds", 600)),
        "ttl_by_intent": dict(cfg.get("ttl_by_intent") or {}),
        "query_ttl_seconds": int(cfg.get("query_ttl_seconds", 45)),
        "rate_limit_enabled": cfg.get("rate_limit_enabled", True) is not False,
        "rate_limit_max": int(cfg.get("rate_limit_max", 30)),
        "rate_limit_window_seconds": int(cfg.get("rate_limit_window_seconds", 300)),
    }


def _cache_key(intent: str, query: str, *, extra: str = "") -> str:
    raw = f"{intent}|{query.strip().lower()}|{extra}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _cache_path(key: str) -> Path:
    return intent_cache_dir() / f"{key}.json"


def _ttl_for_intent(intent: str, cfg: dict[str, Any]) -> int:
    by_intent = cfg.get("ttl_by_intent") or {}
    if intent in by_intent:
        return int(by_intent[intent])
    if intent == "query":
        return int(cfg.get("query_ttl_seconds", 45))
    return int(cfg.get("ttl_seconds", 600))


def get_cached_intent(
    intent: str,
    query: str,
    *,
    settings: Optional[dict[str, Any]] = None,
    extra: str = "",
    ignore_ttl: bool = False,
) -> Optional[dict[str, Any]]:
    cfg = intent_config(settings)
    if not cfg["enabled"]:
        return None
    key = _cache_key(intent, query, extra=extra)
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not ignore_ttl:
        ttl = _ttl_for_intent(intent, cfg)
        if time.time() - float(data.get("ts") or 0) > ttl:
            return None
    payload = data.get("payload")
    return dict(payload) if isinstance(payload, dict) else None


def put_cached_intent(
    intent: str,
    query: str,
    payload: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    extra: str = "",
) -> None:
    cfg = intent_config(settings)
    if not cfg["enabled"]:
        return
    intent_cache_dir().mkdir(parents=True, exist_ok=True)
    key = _cache_key(intent, query, extra=extra)
    _cache_path(key).write_text(
        json.dumps(
            {
                "intent": intent,
                "query": query,
                "extra": extra,
                "ts": time.time(),
                "payload": payload,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _rate_path() -> Path:
    return intent_cache_dir() / _RATE_FILE


def _load_rate_window() -> list[float]:
    path = _rate_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rows = data.get("timestamps")
    if not isinstance(rows, list):
        return []
    out: list[float] = []
    for row in rows:
        try:
            out.append(float(row))
        except (TypeError, ValueError):
            continue
    return out


def _save_rate_window(timestamps: list[float]) -> None:
    intent_cache_dir().mkdir(parents=True, exist_ok=True)
    _rate_path().write_text(
        json.dumps({"ts": time.time(), "timestamps": timestamps}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def check_rate_limit(settings: Optional[dict[str, Any]] = None) -> tuple[bool, Optional[str]]:
    cfg = intent_config(settings)
    if not cfg["rate_limit_enabled"]:
        return True, None
    now = time.time()
    window = cfg["rate_limit_window_seconds"]
    max_calls = cfg["rate_limit_max"]
    recent = [t for t in _load_rate_window() if now - t < window]
    if len(recent) >= max_calls:
        return False, "rate_limited"
    return True, None


def record_intent_call(settings: Optional[dict[str, Any]] = None) -> None:
    cfg = intent_config(settings)
    if not cfg["rate_limit_enabled"]:
        return
    now = time.time()
    window = cfg["rate_limit_window_seconds"]
    recent = [t for t in _load_rate_window() if now - t < window]
    recent.append(now)
    _save_rate_window(recent)


def clear_intent_cache() -> None:
    """Remove cache files (tests)."""
    cache_dir = intent_cache_dir()
    if not cache_dir.exists():
        return
    for path in cache_dir.glob("*.json"):
        path.unlink(missing_ok=True)


def run_intent_cached(
    intent: str,
    query: str,
    fetch_fn: Callable[[], dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
    extra: str = "",
) -> dict[str, Any]:
    """Generic TTL + rate-limit wrapper for high-intent upstream calls."""
    cache_cfg = intent_config(settings)
    query_s = str(query or "").strip()
    if cache_cfg["enabled"]:
        cached = get_cached_intent(intent, query_s, settings=settings, extra=extra)
        if cached is not None:
            hit = dict(cached)
            hit["from_cache"] = True
            return hit

        allowed, reason = check_rate_limit(settings)
        if not allowed:
            stale = get_cached_intent(intent, query_s, settings=settings, extra=extra, ignore_ttl=True)
            if stale is not None:
                hit = dict(stale)
                hit["from_cache"] = True
                hit["rate_limited"] = True
                return hit
            return {
                "intent": intent,
                "query": query_s,
                "skipped": True,
                "reason": reason,
                "items": [],
            }

    out = fetch_fn()
    if cache_cfg["enabled"] and not out.get("skipped"):
        record_intent_call(settings)
        put_cached_intent(intent, query_s, out, settings=settings, extra=extra)
    return out

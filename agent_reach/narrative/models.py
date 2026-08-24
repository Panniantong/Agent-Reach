# -*- coding: utf-8 -*-
"""Shared constants and small validation helpers for the narrative subsystem."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

CLAIM_TAGS = ("KNOWN", "COMPUTED", "INFERRED", "COMMON", "FRAME", "GUESS")
CONFIDENCE_LEVELS = ("HIGH", "MED", "LOW", "VERY LOW", "UNKNOWN")
VERIFICATION_STATES = (
    "pending",
    "reviewed_hypothesis",
    "verified",
    "rejected",
    "disputed",
)
PROBABILITY_STATUSES = ("calibrated", "insufficient_data", "invalid")
HORIZONS = ("quarter", "1y", "3y", "5y")
RESOLUTION_KINDS = ("auto", "human_override")
SCOPE_TYPES = ("macro", "sector", "ticker", "crypto")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def require_choice(value: str, choices: tuple[str, ...], field: str) -> str:
    normalized = str(value or "").strip()
    if normalized not in choices:
        raise ValueError(f"{field} must be one of {', '.join(choices)}")
    return normalized


def json_safe(value: Any) -> Any:
    """Return JSON-compatible values without silently stringifying unknown objects."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")

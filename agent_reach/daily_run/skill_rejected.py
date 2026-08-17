# -*- coding: utf-8
"""Rejected strategy guardrails (DSH rejected Agent Notes style)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_REJECTED_PATH = Path.home() / ".agent-reach" / "daily_run" / "rejected_strategies.jsonl"


def rejected_path() -> Path:
    return _REJECTED_PATH


def _normalize_title(title: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "", str(title or "").lower())
    return raw[:64]


def load_rejected_records(*, limit: int = 200) -> list[dict[str, Any]]:
    if not _REJECTED_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in _REJECTED_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return rows[-limit:]


def rejected_title_keys() -> set[str]:
    keys: set[str] = set()
    for row in load_rejected_records():
        key = _normalize_title(str(row.get("title") or ""))
        if key:
            keys.add(key)
    return keys


def is_rejected_title(title: str) -> bool:
    key = _normalize_title(title)
    return bool(key) and key in rejected_title_keys()


_BUY_BLOCK_PHRASES: tuple[str, ...] = (
    "接飞刀",
    "加大仓位",
    "激进建仓",
    "满仓进攻",
    "逆势加仓",
)


def trade_blocked_by_rejected(
    action: str,
    *,
    code: str = "",
    name: str = "",
    settings: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Return rejected strategy title if trade action should be blocked."""
    harness_cfg = dict((settings or {}).get("harness") or {})
    if harness_cfg.get("runtime_rejected_guard", True) is False:
        return None

    action = str(action or "").lower()
    if action != "buy":
        return None

    for label in (name, code):
        if label and is_rejected_title(str(label)):
            return str(label)

    for row in load_rejected_records():
        title = str(row.get("title") or "")
        reason = str(row.get("reason") or "")
        blob = f"{title} {reason}"
        if any(p in blob for p in _BUY_BLOCK_PHRASES):
            return title or reason
    return None


def add_rejected_strategy(
    title: str,
    reason: str,
    *,
    week_start: str = "",
    week_end: str = "",
    source: str = "weekly",
) -> dict[str, Any]:
    record = {
        "id": f"rej_{len(load_rejected_records()) + 1:04d}",
        "title": str(title).strip(),
        "reason": str(reason).strip(),
        "week_start": week_start,
        "week_end": week_end,
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _REJECTED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_REJECTED_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    try:
        from agent_reach.daily_run.rejected_strategies_harness import apply_rejected_strategies_harness_refinement
        from agent_reach.daily_run.settings import load_settings

        apply_rejected_strategies_harness_refinement(
            title=str(title).strip(),
            reason=str(reason).strip(),
            source=source,
            settings=load_settings(),
        )
    except Exception:
        pass

    return record


def filter_rejected_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop improvements/skill items whose title is in rejected library."""
    keys = rejected_title_keys()
    if not keys:
        return list(items), []
    kept: list[dict[str, Any]] = []
    blocked: list[str] = []
    for item in items:
        title = str(item.get("title") or "")
        key = _normalize_title(title)
        if key and key in keys:
            blocked.append(title)
            continue
        kept.append(item)
    return kept, blocked


def render_rejected_markdown(*, limit: int = 8) -> str:
    rows = load_rejected_records(limit=limit)
    if not rows:
        return ""
    lines = ["### ⛔ 已证伪策略（勿重复写回）", ""]
    for row in reversed(rows[-limit:]):
        title = row.get("title") or "?"
        reason = row.get("reason") or ""
        lines.append(f"- **{title}** — {reason}")
    lines.append("")
    return "\n".join(lines)

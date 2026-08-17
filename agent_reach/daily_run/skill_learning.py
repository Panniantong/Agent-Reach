# -*- coding: utf-8
"""Dedupe / supersession helpers for weekly skill_learning items."""

from __future__ import annotations

import re
from typing import Any


def _normalize_title(title: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "", str(title or "").lower())
    return raw[:48]


def dedupe_skill_learning_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop duplicate titles; later item wins (supersession within same weekly batch)."""
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in items:
        key = _normalize_title(str(item.get("title") or ""))
        if not key:
            key = f"item_{len(order)}"
        if key not in by_key:
            order.append(key)
        by_key[key] = item
    return [by_key[k] for k in order]


def filter_superseded_skill_learning(
    new_items: list[dict[str, Any]],
    existing_titles: list[str],
) -> list[dict[str, Any]]:
    """Skip new items whose normalized title already exists in skill/playbook."""
    existing = {_normalize_title(t) for t in existing_titles if t}
    out: list[dict[str, Any]] = []
    for item in dedupe_skill_learning_items(new_items):
        key = _normalize_title(str(item.get("title") or ""))
        if key and key in existing:
            continue
        out.append(item)
    return out

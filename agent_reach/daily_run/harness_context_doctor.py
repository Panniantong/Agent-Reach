# -*- coding: utf-8
"""Harness duplicate/conflict scan before apply (dsh-context-doctor style)."""

from __future__ import annotations

import re
from typing import Any, Optional

HarnessKind = str


def _harness_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict(((settings or {}).get("harness") or {}))


def context_doctor_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    raw = dict(_harness_cfg(settings).get("context_doctor") or {})
    return {
        "enabled": raw.get("enabled", True) is not False,
        "similarity_threshold": float(raw.get("similarity_threshold") or 0.86),
        "min_chars": int(raw.get("min_chars") or 12),
    }


def normalize_harness_text(text: str) -> str:
    lowered = str(text or "").strip().lower()
    lowered = lowered.replace("_", " ")
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"[¥￥,，。；;：:（）()【】\[\]]+", "", lowered)
    return lowered


def _token_set(text: str) -> set[str]:
    norm = normalize_harness_text(text)
    if not norm:
        return set()
    return {tok for tok in re.split(r"[\s·|/]+", norm) if len(tok) >= 2}


def text_similarity(a: str, b: str) -> float:
    na = normalize_harness_text(a)
    nb = normalize_harness_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if shorter in longer and len(shorter) / max(len(longer), 1) >= 0.6:
        return 0.92
    ta = _token_set(a)
    tb = _token_set(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _collect_existing_contents(state: Any, kind: HarnessKind) -> list[str]:
    entries = (getattr(state, "entries", None) or {}).get(kind) or {}
    out: list[str] = []
    for raw in entries.values():
        content = getattr(raw, "content", None) if not isinstance(raw, dict) else raw.get("content")
        text = str(content or "").strip()
        if text:
            out.append(text)
    return out


def dedupe_incoming_texts(
    texts: list[str],
    existing: list[str],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[list[str], dict[str, Any]]:
    """Drop lines near-duplicating existing harness entries or earlier lines in batch."""
    cfg = context_doctor_cfg(settings)
    if not cfg["enabled"]:
        return list(texts), {"enabled": False}

    kept: list[str] = []
    dropped: list[str] = []
    corpus = list(existing)
    min_chars = cfg["min_chars"]
    threshold = cfg["similarity_threshold"]

    for line in texts:
        text = str(line or "").strip()
        if not text:
            continue
        if len(text) < min_chars:
            kept.append(text)
            corpus.append(text)
            continue
        duplicate = False
        for prior in corpus:
            sim = text_similarity(text, prior)
            if sim >= threshold:
                dropped.append(text[:80])
                duplicate = True
                break
        if not duplicate:
            kept.append(text)
            corpus.append(text)

    return kept, {
        "enabled": True,
        "input_count": len([x for x in texts if str(x or "").strip()]),
        "kept_count": len(kept),
        "dropped_count": len(dropped),
        "dropped_preview": dropped[:6],
        "similarity_threshold": threshold,
    }


def dedupe_kind_texts_against_state(
    texts: list[str],
    state: Any,
    kind: HarnessKind,
    *,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[list[str], dict[str, Any]]:
    existing = _collect_existing_contents(state, kind)
    kept, meta = dedupe_incoming_texts(texts, existing, settings=settings)
    meta["kind"] = kind
    return kept, meta

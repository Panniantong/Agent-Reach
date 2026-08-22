# -*- coding: utf-8
"""Markdown/report coherence checks — candidate table vs recommendation cross-validation."""

from __future__ import annotations

import re
from typing import Any, Optional

from agent_reach.daily_run.snapshot_builder import _normalize_code

_CODE_RE = re.compile(r"\b(\d{6})\b")
_BUY_PHRASES = ("买入", "加仓", "可做", "追涨", "建仓")
_AVOID_PHRASES = ("回避", "减仓", "清仓", "止损")


def report_coherence_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    cfg = (settings or {}).get("report_quality_gate") or {}
    if cfg.get("enabled") is False:
        return False
    qg = (settings or {}).get("quality_gate") or {}
    return qg.get("coherence_enabled", True) is not False


def _report_watchlist_codes(report: dict[str, Any], snapshot: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for block in (
        report.get("watchlist"),
        (report.get("portfolio") or {}).get("watchlist"),
        snapshot.get("watchlist"),
        (snapshot.get("portfolio") or {}).get("watchlist"),
    ):
        for row in block or []:
            if isinstance(row, dict) and row.get("code"):
                codes.add(_normalize_code(str(row["code"])))
    return {c for c in codes if c}


def _holding_codes(report: dict[str, Any], snapshot: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for block in (
        (report.get("portfolio") or {}).get("holdings"),
        (snapshot.get("portfolio") or {}).get("holdings"),
    ):
        for row in block or []:
            if isinstance(row, dict) and row.get("code"):
                codes.add(_normalize_code(str(row["code"])))
    return {c for c in codes if c}


def _candidate_pool_codes(snapshot: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    update = snapshot.get("watchlist_candidates_update") or {}
    for row in update.get("candidates") or []:
        if isinstance(row, dict) and row.get("code"):
            codes.add(_normalize_code(str(row["code"])))
    for row in snapshot.get("weekly_watchlist_candidates") or []:
        if isinstance(row, dict) and row.get("code"):
            codes.add(_normalize_code(str(row["code"])))
    return {c for c in codes if c}


def _recommendation_text(report: dict[str, Any]) -> str:
    parts = [
        str(report.get("reasoning") or ""),
        str(report.get("macro_summary") or ""),
    ]
    narrative = report.get("llm_narrative") or {}
    if isinstance(narrative, dict):
        parts.append(str(narrative.get("summary") or ""))
        parts.extend(str(x) for x in (narrative.get("focus_points") or []))
    return " ".join(p for p in parts if p)


def validate_report_coherence(
    report: dict[str, Any],
    snapshot: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> list[str]:
    """Cross-check recommendation text vs watchlist / candidate pool."""
    if not report_coherence_enabled(settings):
        return []

    snap = snapshot or {}
    cfg = settings or {}
    labels = cfg.get("verdict_labels") or {}
    buy_label = labels.get("buy", "可做")
    avoid_label = labels.get("avoid", "回避")

    primary = _normalize_code(str(report.get("code") or snap.get("code") or ""))
    verdict = str(report.get("verdict") or "")
    text = _recommendation_text(report)
    mentioned = {_normalize_code(m) for m in _CODE_RE.findall(text)}
    mentioned.discard("")

    watchlist_codes = _report_watchlist_codes(report, snap)
    holding_codes = _holding_codes(report, snap)
    candidate_codes = _candidate_pool_codes(snap)
    allowed = watchlist_codes | holding_codes | candidate_codes
    if primary:
        allowed.add(primary)

    warnings: list[str] = []

    if verdict == buy_label:
        for code in sorted(mentioned):
            if code not in allowed:
                warnings.append(f"推荐段提及 {code} 不在持仓/观察池/候选池")

    if verdict == avoid_label and any(p in text for p in _BUY_PHRASES):
        if not any(p in text for p in _AVOID_PHRASES):
            warnings.append("标签为回避但推荐段含看多表述")

    if candidate_codes and mentioned:
        outside = mentioned - candidate_codes - watchlist_codes - holding_codes
        if primary:
            outside.discard(primary)
        if outside and verdict == buy_label:
            sample = "、".join(sorted(outside)[:3])
            warnings.append(f"候选池未覆盖推荐提及标的：{sample}")

    return warnings


def validate_report_coherence_strict(
    report: dict[str, Any],
    snapshot: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[list[str], bool]:
    """Return warnings and whether push should be blocked."""
    warnings = validate_report_coherence(report, snapshot, settings)
    cfg = (settings or {}).get("report_quality_gate") or {}
    block = bool(warnings) and cfg.get("block_on_coherence_fail", False) is True
    return warnings, block

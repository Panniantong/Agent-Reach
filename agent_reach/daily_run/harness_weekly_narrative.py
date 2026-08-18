# -*- coding: utf-8
"""Deterministic weekly harness narrative from apply_audit + refinements (DSH period-report)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


def _harness_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    if settings is None:
        try:
            from agent_reach.daily_run.settings import load_settings

            settings = load_settings()
        except Exception:
            settings = {}
    return dict((settings or {}).get("harness") or {})


def weekly_narrative_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = _harness_cfg(settings)
    raw = dict(cfg.get("weekly_narrative") or {})
    return {
        "enabled": raw.get("enabled", True) is not False,
        "append_to_weekly_card": raw.get("append_to_weekly_card", True) is not False,
        "audit_days": max(1, int(raw.get("audit_days") or 7)),
    }


def _audit_path() -> Path:
    from agent_reach.daily_run.harness_apply_gate import _audit_path as audit_path

    return audit_path()


def _parse_iso_day(value: str) -> Optional[date]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw).date()
    except ValueError:
        if len(raw) >= 10:
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                return None
    return None


def load_apply_audit_in_window(
    *,
    week_start: Optional[str] = None,
    week_end: Optional[str] = None,
    days: int = 7,
) -> list[dict[str, Any]]:
    path = _audit_path()
    if not path.exists():
        return []

    start_day: Optional[date] = _parse_iso_day(week_start or "")
    end_day: Optional[date] = _parse_iso_day(week_end or "")
    if start_day and not end_day:
        end_day = start_day + timedelta(days=max(1, days) - 1)
    if end_day and not start_day:
        start_day = end_day - timedelta(days=max(1, days) - 1)
    if not start_day or not end_day:
        end_day = datetime.now(timezone.utc).date()
        start_day = end_day - timedelta(days=max(1, days) - 1)

    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        day = _parse_iso_day(str(row.get("at") or ""))
        if day is None or day < start_day or day > end_day:
            continue
        out.append(row)
    return out


def build_weekly_harness_narrative(
    *,
    week_start: Optional[str] = None,
    week_end: Optional[str] = None,
    harness_result: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = weekly_narrative_cfg(settings)
    audit_rows = load_apply_audit_in_window(
        week_start=week_start,
        week_end=week_end,
        days=cfg["audit_days"],
    )

    job_counts: Counter[str] = Counter()
    total_changes = 0
    gate_blocks = 0
    admission_rejects = 0
    snapshots = 0

    for row in audit_rows:
        job = str(row.get("job") or "unknown")
        job_counts[job] += 1
        total_changes += int(row.get("changes") or 0)
        gate = row.get("gate") or {}
        if gate.get("blocked_kinds"):
            gate_blocks += 1
        admission = row.get("admission") or gate.get("admission") or {}
        if admission.get("rejected_edits"):
            admission_rejects += len(admission["rejected_edits"])
        if row.get("snapshot_path") or gate.get("snapshot_path"):
            snapshots += 1

    session_layers = 0
    if harness_result:
        from agent_reach.daily_run.harness import _collect_harness_refinement_layers

        session_layers = len(_collect_harness_refinement_layers(harness_result))

    top_jobs = job_counts.most_common(6)
    return {
        "enabled": cfg["enabled"],
        "week_start": week_start,
        "week_end": week_end,
        "audit_events": len(audit_rows),
        "total_changes": total_changes,
        "session_layers": session_layers,
        "gate_blocks": gate_blocks,
        "admission_rejects": admission_rejects,
        "snapshots": snapshots,
        "jobs": dict(top_jobs),
    }


def format_weekly_harness_narrative_markdown(
    narrative: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> str:
    cfg = weekly_narrative_cfg(settings)
    if not cfg.get("enabled") or not narrative:
        return ""

    ws = narrative.get("week_start") or ""
    we = narrative.get("week_end") or ""
    window = f"{ws}~{we}" if ws and we else "近 7 日"

    lines = [
        "",
        f"**Harness 周度叙事 · {window}**",
        "",
        f"- 审计事件 **{int(narrative.get('audit_events') or 0)}** 次 · "
        f"累计变更 **{int(narrative.get('total_changes') or 0)}** 项",
    ]
    if narrative.get("session_layers"):
        lines.append(f"- 本周 session refine **{int(narrative['session_layers'])}** 层")
    if narrative.get("gate_blocks"):
        lines.append(f"- Apply gate 拦截 **{int(narrative['gate_blocks'])}** 次")
    if narrative.get("admission_rejects"):
        lines.append(f"- Layer B Admission 拒绝 **{int(narrative['admission_rejects'])}** 条 edits")
    if narrative.get("snapshots"):
        lines.append(f"- 改前快照 **{int(narrative['snapshots'])}** 份")

    jobs = narrative.get("jobs") or {}
    if jobs:
        job_bits = [f"{name}×{count}" for name, count in list(jobs.items())[:6]]
        lines.append(f"- Job 分布：{', '.join(job_bits)}")

    return "\n".join(lines)

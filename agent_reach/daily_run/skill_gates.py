# -*- coding: utf-8
"""Mechanical gates for Saturday skill writeback (DSH verify-gates style)."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

from agent_reach.daily_run.skill_improvements_apply import (
    REQUIRED_SKILL_SECTIONS,
    build_next_week_playbook_block,
    PLAYBOOK_PREFIX,
)
from agent_reach.daily_run.skill_writeback import (
    EXPERIENCE_HEADER,
    build_weekly_experience_block,
)

_DEFAULT_MAX_LINES = 400
_PLAYBOOK_MARKERS = (PLAYBOOK_PREFIX, "### 🔧 流程改进")
_EXPERIENCE_MARKERS = ("周复盘（周六自动沉淀）", "**情况说明：**")


def _gates_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict(((settings or {}).get("weekly_report") or {}).get("skill_gates") or {})


def gates_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    return _gates_cfg(settings).get("enabled", True) is not False


def _block_fingerprint(block: str) -> str:
    normalized = re.sub(r"\s+", " ", block.strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def run_skill_gates(
    skill_text: str,
    report: dict[str, Any],
    *,
    applied_config: Optional[list[str]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Validate skill structure after weekly writeback; return gate result."""
    cfg = _gates_cfg(settings)
    if not gates_enabled(settings):
        return {"ok": True, "skipped": True, "reason": "skill_gates disabled"}

    failures: list[str] = []
    warnings: list[str] = []

    if cfg.get("require_sections", True) is not False:
        missing = [sec for sec in REQUIRED_SKILL_SECTIONS if sec not in skill_text]
        if missing:
            failures.append(f"缺少必备章节：{', '.join(missing[:3])}")

    max_lines = int(cfg.get("max_lines") or _DEFAULT_MAX_LINES)
    line_count = len(skill_text.splitlines())
    if line_count > max_lines:
        failures.append(f"skill 行数 {line_count} 超过上限 {max_lines}")

    if cfg.get("require_playbook", True) is not False:
        for marker in _PLAYBOOK_MARKERS:
            if marker not in skill_text:
                failures.append(f"playbook 缺少标记：{marker[:24]}")

    if cfg.get("require_experience", True) is not False:
        if EXPERIENCE_HEADER not in skill_text:
            failures.append("缺少经验沉淀库章节")
        for marker in _EXPERIENCE_MARKERS:
            if marker not in skill_text:
                warnings.append(f"experience 缺少标记：{marker[:24]}")

    week_start = str(report.get("week_start") or "")
    week_end = str(report.get("week_end") or "")
    if week_start and week_end:
        week_hdr = f"{week_start} ~ {week_end}"
        if week_hdr not in skill_text:
            failures.append(f"未找到本周复盘块：{week_hdr}")

    if cfg.get("snapshot_blocks", True) is not False:
        fingerprints: dict[str, str] = {}
        try:
            pb = build_next_week_playbook_block(report, applied_config or [])
            exp = build_weekly_experience_block(report)
        except Exception as exc:
            failures.append(f"snapshot 块生成失败：{exc}")
        else:
            if len(pb.splitlines()) > int(cfg.get("max_playbook_lines") or 45):
                failures.append(f"playbook 块行数 {len(pb.splitlines())} 超限")
            if len(exp.splitlines()) > int(cfg.get("max_experience_lines") or 55):
                failures.append(f"experience 块行数 {len(exp.splitlines())} 超限")
            fingerprints = {
                "playbook": _block_fingerprint(pb),
                "experience": _block_fingerprint(exp),
            }
    else:
        fingerprints = {}

    ok = not failures
    return {
        "ok": ok,
        "failures": failures,
        "warnings": warnings,
        "line_count": line_count,
        "max_lines": max_lines,
        "fingerprints": fingerprints,
        "block_weekly_push": bool(cfg.get("block_weekly_push", True)) and not ok,
    }


def format_gate_alert_markdown(gate_result: dict[str, Any]) -> str:
    if gate_result.get("ok") is not False:
        return ""
    lines = [
        "**⛔ Skill 机械门禁未通过**",
        "",
    ]
    for item in gate_result.get("failures") or []:
        lines.append(f"- {item}")
    for item in gate_result.get("warnings") or []:
        lines.append(f"- ⚠️ {item}")
    lines.append("")
    lines.append("周报飞书推送已阻断；请检查 skill 写回后手工补跑。")
    return "\n".join(lines)

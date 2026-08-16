# -*- coding: utf-8
"""Mechanical gates for Saturday skill writeback (DSH verify-gates style)."""

from __future__ import annotations

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
    week_section_header,
)

_DEFAULT_MAX_LINES = 400
_PLAYBOOK_MARKERS = (PLAYBOOK_PREFIX, "### 🔧 流程改进")
_EXPERIENCE_MARKERS = ("周复盘（周六自动沉淀）", "**情况说明：**")


def _gates_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict(((settings or {}).get("weekly_report") or {}).get("skill_gates") or {})


def gates_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    return _gates_cfg(settings).get("enabled", True) is not False


def _block_fingerprint(block: str) -> str:
    from agent_reach.daily_run.skill_fragments import block_fingerprint

    return block_fingerprint(block)


def _extract_playbook_block(skill_text: str) -> str:
    idx = 0
    best = ""
    while True:
        pos = skill_text.find(PLAYBOOK_PREFIX, idx)
        if pos < 0:
            break
        line_end = skill_text.find("\n", pos)
        search_from = line_end + 1 if line_end >= 0 else pos + len(PLAYBOOK_PREFIX)
        tail = skill_text[search_from:]
        ends = [len(skill_text)]
        for pattern in (r"\n### 📅 ", r"\n---\n", r"\n## "):
            match = re.search(pattern, tail)
            if match:
                ends.append(search_from + match.start())
        chunk = skill_text[pos : min(ends)]
        if len(chunk) > len(best):
            best = chunk
        idx = pos + len(PLAYBOOK_PREFIX)
    return best


def _extract_experience_block(skill_text: str, week_start: str, week_end: str) -> str:
    if not week_start or not week_end:
        return ""
    header = week_section_header(week_start, week_end)
    if header not in skill_text:
        return ""
    start = skill_text.find(header)
    tail = skill_text[start:]
    ends = [len(tail)]
    for pattern in (r"\n---\n", r"\n### 📅 ", r"\n## "):
        match = re.search(pattern, tail[len(header) :])
        if match:
            ends.append(len(header) + match.start())
    return skill_text[start : start + min(ends)]


def _verify_written_fingerprints(
    *,
    expected: dict[str, str],
    playbook_text: str,
    experience_text: str,
    skill_text: str,
    week_start: str,
    week_end: str,
    use_external: bool,
) -> list[str]:
    failures: list[str] = []
    written_pb = playbook_text if use_external else _extract_playbook_block(skill_text)
    written_exp = experience_text if use_external else _extract_experience_block(
        skill_text, week_start, week_end
    )
    if expected.get("playbook") and _block_fingerprint(written_pb) != expected["playbook"]:
        failures.append("playbook 写入内容与 snapshot fingerprint 不一致")
    if expected.get("experience") and _block_fingerprint(written_exp) != expected["experience"]:
        failures.append("experience 写入内容与 snapshot fingerprint 不一致")
    return failures


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

    from agent_reach.daily_run.skill_fragments import (
        external_enabled,
        read_experience_fragment,
        read_playbook_fragment,
    )

    use_external = external_enabled(settings)
    playbook_text = read_playbook_fragment() if use_external else skill_text
    experience_text = read_experience_fragment() if use_external else skill_text

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
        if use_external and not playbook_text.strip():
            failures.append("playbook 外链片段为空")
        improvements = report.get("process_improvements") or []
        for marker in _PLAYBOOK_MARKERS:
            if marker == "### 🔧 流程改进" and not improvements:
                continue
            if marker not in playbook_text:
                failures.append(f"playbook 缺少标记：{marker[:24]}")

    if cfg.get("require_experience", True) is not False:
        if EXPERIENCE_HEADER not in skill_text:
            failures.append("缺少经验沉淀库章节")
        if use_external and not experience_text.strip():
            failures.append("experience 外链片段为空")
        for marker in _EXPERIENCE_MARKERS:
            if marker not in experience_text:
                warnings.append(f"experience 缺少标记：{marker[:24]}")

    week_start = str(report.get("week_start") or "")
    week_end = str(report.get("week_end") or "")
    if week_start and week_end:
        week_hdr = f"{week_start} ~ {week_end}"
        week_target = experience_text if use_external else skill_text
        if week_hdr not in week_target:
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
            if cfg.get("verify_fingerprints", True) is not False:
                failures.extend(
                    _verify_written_fingerprints(
                        expected=fingerprints,
                        playbook_text=playbook_text,
                        experience_text=experience_text,
                        skill_text=skill_text,
                        week_start=week_start,
                        week_end=week_end,
                        use_external=use_external,
                    )
                )
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
        "external_fragments": use_external,
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

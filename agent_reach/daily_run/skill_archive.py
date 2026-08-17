# -*- coding: utf-8
"""Archive old weekly experience blocks from daily_run skill (DSH compaction style)."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.skill_writeback import EXPERIENCE_HEADER, week_section_header

_ARCHIVE_DIR = Path.home() / ".agent-reach" / "daily_run" / "archives" / "skill"
_ARCHIVE_SUMMARY_HEADER = "### 📦 归档摘要（自动 compaction）"
_WEEKLY_HEADER_RE = re.compile(
    r"^### 📅 (?P<start>\d{4}-\d{2}-\d{2}) ~ (?P<end>\d{4}-\d{2}-\d{2}) 周复盘（周六自动沉淀）",
    re.MULTILINE,
)


def archive_dir() -> Path:
    return _ARCHIVE_DIR


def _parse_week_end(header_line: str) -> Optional[str]:
    match = _WEEKLY_HEADER_RE.match(header_line.strip())
    if not match:
        return None
    return match.group("end")


def _section_bounds(text: str, header: str) -> tuple[int, int]:
    start = text.find(header)
    if start < 0:
        return -1, -1
    tail = text[start:]
    ends = [len(tail)]
    for pattern in (r"\n---\n", r"\n### 📅 ", r"\n## "):
        match = re.search(pattern, tail[len(header) :])
        if match:
            ends.append(len(header) + match.start())
    end_rel = min(ends)
    return start, start + end_rel


def list_weekly_review_headers(text: str) -> list[tuple[str, str]]:
    """Return (header_line, week_end) sorted by week_end ascending."""
    rows: list[tuple[str, str]] = []
    for match in _WEEKLY_HEADER_RE.finditer(text):
        header = match.group(0)
        week_end = match.group("end")
        rows.append((header, week_end))
    rows.sort(key=lambda row: row[1])
    return rows


def _week_label_from_block(block: str, fallback: str) -> str:
    match = _WEEKLY_HEADER_RE.search(block)
    if match:
        return f"{match.group('start')}~{match.group('end')}"
    return fallback


def _rule_summarize_block(block: str) -> str:
    picks: list[str] = []
    for line in block.splitlines():
        raw = line.strip().lstrip("*").strip()
        if not raw or raw.startswith("#"):
            continue
        if any(k in raw for k in ("情况说明", "流程改进", "盈亏", "任务覆盖", "强势", "备注")):
            picks.append(raw[:100])
        if len(picks) >= 3:
            break
    if picks:
        return "；".join(picks)[:280]
    compact = block.strip()
    return compact[:120] if compact else "（无摘要）"


def summarize_archived_block(
    block: str,
    *,
    settings: Optional[dict[str, Any]] = None,
) -> str:
    """LLM summary when configured; else deterministic rule summary."""
    cfg = (settings or {}).get("weekly_report") or {}
    if cfg.get("skill_archive_llm_summary", True) is False:
        return _rule_summarize_block(block)

    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(((settings or {}).get("llm_narrative") or {}).get("provider") or "auto")
    if not resolve_chat_provider(provider):
        return _rule_summarize_block(block)

    try:
        payload = chat_json(
            system='你是 daily-run skill compaction 助手。输出 JSON：{"summary":"一句中文摘要，≤120字，含盈亏方向与1条教训"}',
            user=block[:3500],
            provider=provider,
            timeout=int(cfg.get("skill_archive_summary_timeout") or 30),
        )
        if isinstance(payload, dict) and payload.get("summary"):
            return str(payload["summary"]).strip()[:280]
        return _rule_summarize_block(block)
    except Exception:
        return _rule_summarize_block(block)


def _upsert_archive_summary_section(text: str, rows: list[tuple[str, str]]) -> str:
    if not rows or EXPERIENCE_HEADER not in text:
        return text
    lines = [_ARCHIVE_SUMMARY_HEADER, ""]
    for label, summary in rows:
        lines.append(f"* **{label}：** {summary}")
    lines.append("")
    block = "\n".join(lines)

    if _ARCHIVE_SUMMARY_HEADER in text:
        start = text.find(_ARCHIVE_SUMMARY_HEADER)
        end = start + len(block)
        tail = text[start + len(_ARCHIVE_SUMMARY_HEADER) :]
        for pattern in (r"\n### 📅 ", r"\n---\n", r"\n## "):
            match = re.search(pattern, tail)
            if match:
                end = start + len(_ARCHIVE_SUMMARY_HEADER) + match.start()
                break
        return text[:start] + block + text[end:].lstrip("\n")

    pos = text.find(EXPERIENCE_HEADER)
    line_end = text.find("\n", pos)
    intro_end = text.find("\n\n", line_end if line_end >= 0 else pos)
    if intro_end < 0:
        intro_end = len(text)
    return text[:intro_end] + "\n\n" + block + text[intro_end:].lstrip("\n")


def compact_experience_sections(
    text: str,
    *,
    keep_weeks: int = 2,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[str, list[str]]:
    """Move older weekly review blocks to archive dir; keep newest *keep_weeks* in skill."""
    cfg = (settings or {}).get("weekly_report") or {}
    if cfg.get("skill_archive", True) is False:
        return text, []

    keep = int(cfg.get("skill_archive_keep_weeks") or keep_weeks)
    headers = list_weekly_review_headers(text)
    if len(headers) <= keep:
        return text, []

    to_archive = headers[: len(headers) - keep]
    archived_paths: list[str] = []
    summary_rows: list[tuple[str, str]] = []
    new_text = text

    _ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    for header, week_end in to_archive:
        bounds = _section_bounds(new_text, header)
        if bounds[0] < 0:
            continue
        block = new_text[bounds[0] : bounds[1]].strip() + "\n"
        ws = header.split(" ~ ")[0].replace("### 📅 ", "").strip()
        we = week_end
        fname = f"{we}_{ws}_weekly_review.md"
        out_path = _ARCHIVE_DIR / fname
        if not out_path.exists():
            out_path.write_text(block, encoding="utf-8")
        archived_paths.append(str(out_path))
        label = _week_label_from_block(block, f"{ws}~{we}")
        summary_rows.append((label, summarize_archived_block(block, settings=settings)))
        new_text = (new_text[: bounds[0]] + new_text[bounds[1] :]).strip() + "\n"

    if summary_rows:
        new_text = _upsert_archive_summary_section(new_text, summary_rows)

    if archived_paths and EXPERIENCE_HEADER in new_text:
        note = (
            f"> 更早周复盘已归档至 `{_ARCHIVE_DIR}`（保留最近 {keep} 周）。"
        )
        if note not in new_text:
            pos = new_text.find(EXPERIENCE_HEADER)
            line_end = new_text.find("\n", pos)
            if line_end < 0:
                line_end = len(new_text)
            intro_end = new_text.find("\n\n", line_end)
            if intro_end < 0:
                intro_end = line_end
            new_text = new_text[:intro_end] + "\n\n" + note + new_text[intro_end:]

    return new_text.rstrip() + "\n", archived_paths


def annotate_experience_refinement_id(
    text: str,
    *,
    week_start: str,
    week_end: str,
    refinement_id: str,
) -> str:
    """Append harness refinement_id audit line to the weekly experience block."""
    if not refinement_id:
        return text
    header = week_section_header(week_start, week_end)
    if header not in text:
        return text
    audit_line = f"*   **Harness refinement_id：** `{refinement_id}`"
    if audit_line in text:
        return text
    start, end = _section_bounds(text, header)
    if start < 0:
        return text
    block = text[start:end]
    block = block.rstrip() + "\n" + audit_line + "\n"
    return text[:start] + block + text[end:]

# -*- coding: utf-8
"""Saturday weekly report → append summarized experience to daily_run skill files."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

EXPERIENCE_HEADER = "## 🧠 股票大师实战经验沉淀库"
OPS_HEADER = "## 🛠️ 运维与排障指南"
WEEKLY_TAG = "周六自动沉淀"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def week_section_header(week_start: str, week_end: str) -> str:
    return f"### 📅 {week_start} ~ {week_end} 周复盘（{WEEKLY_TAG}）"


def resolve_skill_writeback_paths(settings: Optional[dict[str, Any]] = None) -> list[Path]:
    """Skill markdown files to update after Saturday weekly."""
    cfg = (settings or {}).get("weekly_report") or {}
    explicit = cfg.get("skill_writeback_paths") or []
    if explicit:
        return [Path(p).expanduser() for p in explicit]

    paths: list[Path] = [_repo_root() / "agent_reach" / "skill" / "daily_run_skill.md"]
    for candidate in (
        Path.home() / ".agents" / "skills" / "daily-run" / "SKILL.md",
        Path.home() / ".agents" / "skills" / "daily-run-skill" / "SKILL.md",
        Path.home() / ".openclaw" / "skills" / "daily-run" / "SKILL.md",
    ):
        if candidate.exists() and candidate not in paths:
            paths.append(candidate)
    return paths


def _load_rules_summary(limit: int = 5) -> list[str]:
    path = Path.home() / ".agent-reach" / "daily_run" / "experience" / "rules_summary.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rules = list(data.get("rules") or [])
        return rules[-limit:]
    except (json.JSONDecodeError, OSError):
        return []


def _format_money(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"¥{value:,.2f}"


def _format_pnl_line(report: dict[str, Any]) -> str:
    pnl = report.get("weekly_pnl")
    pct = report.get("weekly_pnl_pct")
    start = report.get("start_total")
    end = report.get("end_total")
    if pnl is None:
        return "本周盈亏数据不可用（可能缺少周初早盘 manifest）"
    sign = "+" if float(pnl) >= 0 else ""
    pct_part = f"（{sign}{pct}%）" if pct is not None else ""
    range_part = ""
    if start is not None and end is not None:
        range_part = f"，周初 {_format_money(float(start))} → 周末 {_format_money(float(end))}"
    return f"组合净值 {sign}{_format_money(float(pnl))}{pct_part}{range_part}"


def _holdings_line(holdings: list[dict[str, Any]], limit: int = 4) -> str:
    if not holdings:
        return "无持仓记录"
    parts = []
    for row in holdings[:limit]:
        name = row.get("name") or row.get("code") or "?"
        code = row.get("code") or ""
        chg = row.get("change_pct")
        if chg is not None:
            parts.append(f"{name} ({code}) {float(chg):+.2f}%")
        else:
            parts.append(f"{name} ({code})")
    return "、".join(parts)


def _hot_sectors_line(hot_sectors: list[dict[str, Any]], limit: int = 3) -> str:
    if not hot_sectors:
        return "暂无强势板块数据"
    parts = []
    for row in hot_sectors[:limit]:
        name = row.get("name") or row.get("code") or "?"
        chg = row.get("change_pct")
        if chg is not None:
            parts.append(f"{name} {float(chg):+.2f}%")
        else:
            parts.append(str(name))
    return "、".join(parts)


def _dedupe_text_lines(items: list[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in reversed(items):
        text = str(item or "").strip()
        if not text:
            continue
        key = re.sub(r"\d{4}-\d{2}-\d{2}", "", text)
        key = re.sub(r"MSS=[\d.]+", "MSS=", key)
        key = re.sub(r"价格变动 [-\d.]+%", "价格变动", key)
        key = key[:96]
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    out.reverse()
    return out[-limit:]


def _job_stats(report: dict[str, Any]) -> str:
    mss = report.get("mss_summary") or []
    morning = sum(1 for m in mss if m.get("job") == "morning")
    close = sum(1 for m in mss if m.get("job") == "close")
    intraday = sum(1 for m in mss if m.get("job") == "intraday")
    return f"早盘 {morning}/5、收盘 {close}/5、盘中 {intraday} 次"


def build_weekly_experience_block(report: dict[str, Any]) -> str:
    """Render one weekly experience section for skill markdown."""
    from agent_reach.daily_run.weekly_report import build_weekly_pnl_explanation

    week_start = str(report.get("week_start") or "")
    week_end = str(report.get("week_end") or "")
    header = week_section_header(week_start, week_end)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        header,
        f"*   **更新时间：** {updated}",
    ]
    ref_id = report.get("harness_refinement_id") or report.get("refinement_id")
    if ref_id:
        lines.append(f"*   **Harness refinement_id：** `{ref_id}`")
    lines.extend(
        [
            "*   **本周盈亏说明：**",
        ]
    )
    for expl in build_weekly_pnl_explanation(report):
        if expl.startswith("  - "):
            lines.append(f"    *   {expl[4:].strip()}")
        elif expl.startswith("- "):
            lines.append(f"*   {expl[2:].strip()}")
        else:
            lines.append(f"*   {expl.strip()}")

    lines.extend(
        [
            f"*   **持股概况：** {_holdings_line(report.get('holdings') or [])}",
            f"*   **强势标的：** {_hot_sectors_line(report.get('hot_sectors') or [])}",
            f"*   **任务覆盖：** {_job_stats(report)}",
        ]
    )

    notes = report.get("notes") or []
    if notes:
        lines.append(f"*   **备注：** {'；'.join(str(n) for n in notes[:3])}")

    snippets = _dedupe_text_lines(list(report.get("experience_snippets") or []), limit=5)
    if snippets:
        lines.append("*   **收盘经验片段：**")
        for snippet in snippets:
            lines.append(f"    *   {snippet}")

    rules = _dedupe_text_lines(_load_rules_summary(), limit=5)
    if rules:
        lines.append("*   **量化规则库（最近）：**")
        for rule in rules:
            lines.append(f"    *   {rule}")

    skill_items = report.get("skill_learning") or []
    if skill_items:
        lines.append("*   **技能学习要点：**")
        for item in skill_items[:5]:
            title = item.get("title") or "技能"
            summary = item.get("summary") or ""
            lines.append(f"    *   **{title}：** {summary}")

    sector_research = report.get("sector_research") or []
    ok_research = [r for r in sector_research if r.get("success") and (r.get("summary") or r.get("hits"))]
    if ok_research:
        lines.append("*   **板块调研摘要：**")
        for row in ok_research[:2]:
            label = row.get("label") or row.get("query") or "调研"
            summary = (row.get("summary") or "")[:160]
            lines.append(f"    *   {label}：{summary}")

    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _find_section_end(text: str, start: int) -> int:
    tail = text[start:]
    patterns = [
        r"\n---\n",
        r"\n### 📅 ",
        r"\n## 🛠️ ",
    ]
    ends = [len(tail)]
    for pattern in patterns:
        match = re.search(pattern, tail[1:])
        if match:
            ends.append(start + 1 + match.start())
    return min(ends)


def _replace_weekly_section(text: str, header: str, block: str) -> str:
    idx = text.find(header)
    if idx < 0:
        return text
    end = _find_section_end(text, idx)
    return text[:idx] + block.rstrip() + "\n\n---\n\n" + text[end:].lstrip("\n-")


def _insert_weekly_section(text: str, block: str) -> str:
    if EXPERIENCE_HEADER not in text:
        if OPS_HEADER in text:
            return text.replace(OPS_HEADER, block.rstrip() + "\n\n---\n\n\n" + OPS_HEADER, 1)
        return text.rstrip() + "\n\n" + block.rstrip() + "\n"

    marker = EXPERIENCE_HEADER
    pos = text.find(marker)
    after = text.find("\n", pos)
    if after < 0:
        return text + "\n\n" + block

    intro_end = text.find("\n\n", after)
    if intro_end < 0:
        intro_end = len(text)

    insertion = "\n\n" + block.rstrip() + "\n\n---\n\n"
    return text[:intro_end] + insertion + text[intro_end:].lstrip("\n")


def patch_skill_file(path: Path, block: str, week_start: str, week_end: str) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    header = week_section_header(week_start, week_end)
    if header in text:
        new_text = _replace_weekly_section(text, header, block)
    else:
        new_text = _insert_weekly_section(text, block)
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True

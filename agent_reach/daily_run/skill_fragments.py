# -*- coding: utf-8
"""External skill fragments — playbook/experience outside canonical skill (token savings)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.skill_writeback import EXPERIENCE_HEADER, week_section_header

FRAGMENTS_DIR = Path.home() / ".agent-reach" / "daily_run" / "skill"
PLAYBOOK_FRAGMENT = FRAGMENTS_DIR / "playbook.md"
EXPERIENCE_FRAGMENT = FRAGMENTS_DIR / "experience_latest.md"
FRAGMENTS_MANIFEST = FRAGMENTS_DIR / "fragments.json"
ARCHIVE_DIR = Path.home() / ".agent-reach" / "daily_run" / "archives" / "skill"

PLAYBOOK_STUB_LINE = "> **动态片段** `~/.agent-reach/daily_run/skill/playbook.md`"
EXPERIENCE_STUB_LINE = "> **动态片段** `~/.agent-reach/daily_run/skill/experience_latest.md`"


def block_fingerprint(block: str) -> str:
    text = str(block or "")
    text = re.sub(r"> 更新时间[^\n]*", "> 更新时间", text)
    text = re.sub(r"\*\*更新时间：\*\*[^\n]*", "**更新时间：**", text)
    normalized = re.sub(r"\s+", " ", text.strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _external_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict(((settings or {}).get("weekly_report") or {}).get("skill_external") or {})


def external_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    return _external_cfg(settings).get("enabled", True) is not False


def read_playbook_fragment() -> str:
    if not PLAYBOOK_FRAGMENT.exists():
        return ""
    return PLAYBOOK_FRAGMENT.read_text(encoding="utf-8")


def read_experience_fragment() -> str:
    if not EXPERIENCE_FRAGMENT.exists():
        return ""
    return EXPERIENCE_FRAGMENT.read_text(encoding="utf-8")


def _archive_experience_fragment(week_start: str, week_end: str) -> Optional[Path]:
    if not EXPERIENCE_FRAGMENT.exists():
        return None
    text = EXPERIENCE_FRAGMENT.read_text(encoding="utf-8").strip()
    if not text:
        return None
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    out = ARCHIVE_DIR / f"{week_end}_{week_start}_weekly_review.md"
    if not out.exists():
        out.write_text(text + "\n", encoding="utf-8")
    return out


def write_fragments(
    *,
    playbook_block: str,
    experience_block: str,
    week_start: str,
    week_end: str,
    refinement_id: str = "",
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Persist dynamic playbook/experience blocks; archive prior experience fragment."""
    FRAGMENTS_DIR.mkdir(parents=True, exist_ok=True)
    archived = _archive_experience_fragment(week_start, week_end)
    PLAYBOOK_FRAGMENT.write_text(playbook_block.rstrip() + "\n", encoding="utf-8")
    EXPERIENCE_FRAGMENT.write_text(experience_block.rstrip() + "\n", encoding="utf-8")
    manifest = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "week_start": week_start,
        "week_end": week_end,
        "refinement_id": refinement_id or "",
        "playbook_path": str(PLAYBOOK_FRAGMENT),
        "experience_path": str(EXPERIENCE_FRAGMENT),
        "archived_previous": str(archived) if archived else "",
        "fingerprints": {
            "playbook": block_fingerprint(playbook_block),
            "experience": block_fingerprint(experience_block),
        },
    }
    FRAGMENTS_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _replace_playbook_stub(text: str, week_start: str, week_end: str) -> str:
    from agent_reach.daily_run.skill_improvements_apply import PLAYBOOK_PREFIX

    stub = (
        f"{PLAYBOOK_PREFIX} · 外链 {week_start}~{week_end}）\n\n"
        f"{PLAYBOOK_STUB_LINE} · 索引 `next_week_playbook.json`\n"
    )
    idx = text.find(PLAYBOOK_PREFIX)
    if idx >= 0:
        end = text.find("\n## ", idx + len(PLAYBOOK_PREFIX))
        if end < 0:
            end = len(text)
        return text[:idx] + stub.rstrip() + "\n\n" + text[end:].lstrip()
    return text


def _replace_experience_stub(text: str) -> str:
    stub = (
        f"{EXPERIENCE_HEADER}\n\n"
        f"{EXPERIENCE_STUB_LINE} · 归档 `~/.agent-reach/daily_run/archives/skill/`\n"
    )
    idx = text.find(EXPERIENCE_HEADER)
    if idx < 0:
        return text.rstrip() + "\n\n" + stub + "\n"
    end = text.find("\n## ", idx + len(EXPERIENCE_HEADER))
    if end < 0:
        end = len(text)
    return text[:idx] + stub.rstrip() + "\n\n" + text[end:].lstrip()


def patch_canonical_stubs(
    path: Path,
    *,
    week_start: str,
    week_end: str,
) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    new_text = _replace_experience_stub(_replace_playbook_stub(text, week_start, week_end))
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def annotate_experience_fragment(
    *,
    week_start: str,
    week_end: str,
    refinement_id: str,
) -> bool:
    if not refinement_id or not EXPERIENCE_FRAGMENT.exists():
        return False
    text = EXPERIENCE_FRAGMENT.read_text(encoding="utf-8")
    header = week_section_header(week_start, week_end)
    if header not in text:
        return False
    audit_line = f"*   **Harness refinement_id：** `{refinement_id}`"
    if audit_line in text:
        return False
    new_text = text.rstrip() + "\n" + audit_line + "\n"
    EXPERIENCE_FRAGMENT.write_text(new_text, encoding="utf-8")
    if FRAGMENTS_MANIFEST.exists():
        try:
            manifest = json.loads(FRAGMENTS_MANIFEST.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {}
        manifest["refinement_id"] = refinement_id
        manifest["annotated_at"] = datetime.now(timezone.utc).isoformat()
        FRAGMENTS_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True

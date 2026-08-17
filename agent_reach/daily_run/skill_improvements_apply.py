# -*- coding: utf-8
"""Apply Saturday weekly learning/improvements to skill + settings + local runtime."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.settings import clear_settings_cache, load_settings, save_user_settings
from agent_reach.daily_run.skill_archive import (
    annotate_experience_refinement_id,
    compact_experience_sections,
)
from agent_reach.daily_run.skill_learning import (
    dedupe_skill_learning_items,
    filter_superseded_skill_learning,
)
from agent_reach.daily_run.skill_rejected import (
    filter_rejected_items,
    render_rejected_markdown,
)
from agent_reach.daily_run.skill_writeback import (
    EXPERIENCE_HEADER,
    OPS_HEADER,
    _find_section_end,
    _repo_root,
    build_weekly_experience_block,
    patch_skill_file,
    resolve_skill_writeback_paths,
    sync_cursor_agent_skills_to_local,
    week_section_header,
)

PLAYBOOK_PREFIX = "## 📋 下周执行清单（周六自动更新"
PLAYBOOK_MANIFEST = Path.home() / ".agent-reach" / "daily_run" / "next_week_playbook.json"
SKILL_CHANGELOG = Path.home() / ".agent-reach" / "daily_run" / "skill_changelog.jsonl"
AGENT_ENTRY_HEADER = "## ⚡ Agent 执行入口"
DECISION_HEADER = "## 📊 决策模型"
PHASE1_HEADER = "## 🛡️ Phase-1 质量工程化"

REQUIRED_SKILL_SECTIONS = (
    AGENT_ENTRY_HEADER,
    PLAYBOOK_PREFIX,
    PHASE1_HEADER,
    DECISION_HEADER,
    EXPERIENCE_HEADER,
    OPS_HEADER,
)


def _normalize_report_for_writeback(report: dict[str, Any], skill_text: str = "") -> dict[str, Any]:
    """Dedupe skill_learning, drop superseded/rejected titles."""
    out = dict(report)
    improvements, blocked_imp = filter_rejected_items(list(out.get("process_improvements") or []))
    out["process_improvements"] = improvements
    items = dedupe_skill_learning_items(list(out.get("skill_learning") or []))
    items, blocked_skill = filter_rejected_items(items)
    out["skill_learning"] = filter_superseded_skill_learning(
        items, _existing_skill_learning_titles(skill_text)
    )
    blocked = blocked_imp + blocked_skill
    if blocked:
        out["_rejected_blocked"] = blocked
        try:
            from agent_reach.daily_run.rejected_strategies_harness import apply_rejected_strategies_harness_refinement
            from agent_reach.daily_run.settings import load_settings

            apply_rejected_strategies_harness_refinement(
                blocked=blocked,
                settings=load_settings(),
            )
        except Exception:
            pass
    return out


def _existing_skill_learning_titles(skill_text: str) -> list[str]:
    """Extract titles only from skill-learning sections (avoid matching workflow prose)."""
    titles: list[str] = []
    for match in re.finditer(
        r"(?:### 🎓 技能学习|\*\*技能学习要点：\*\*)[\s\S]*?(?=\n### |\n## |\Z)",
        skill_text,
    ):
        for title_match in re.finditer(r"\*\*([^*]+)：\*\*", match.group(0)):
            titles.append(title_match.group(1).strip())
    return titles


def audit_supersession_harness(report: dict[str, Any]) -> dict[str, Any]:
    """Flag improvements already captured in harness playbook/plan."""
    from agent_reach.daily_run.harness import load_harness

    state = load_harness()
    known: set[str] = set()
    for kind in ("playbook", "plan", "policy"):
        for entry in (state.entries.get(kind) or {}).values():
            title = str(entry.title or "")
            content = str(entry.content or "")
            known.add(title[:24])
            known.add(content[:24])
    duplicates: list[str] = []
    for item in report.get("process_improvements") or []:
        title = str(item.get("title") or "")
        if any(title[:16] and title[:16] in k for k in known):
            duplicates.append(title)
    return {"harness_duplicates": duplicates}


def build_next_week_playbook_block(
    report: dict[str, Any],
    applied_config: list[str],
) -> str:
    week_start = str(report.get("week_start") or "")
    week_end = str(report.get("week_end") or "")
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"{PLAYBOOK_PREFIX} · 复盘 {week_start}~{week_end}）",
        "",
        f"> 更新时间 {updated}。Agent 与 daily-run 下周须优先执行；带 ✅ 的参数已自动写入 settings。",
        "",
    ]

    if applied_config:
        lines.extend(["### ⚙️ 参数自动调整（已应用）", ""])
        for note in applied_config:
            lines.append(f"- ✅ {note}")
        lines.append("")

    improvements = report.get("process_improvements") or []
    if improvements:
        lines.extend(["### 🔧 流程改进", ""])
        for item in improvements:
            badge = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                str(item.get("priority") or ""), "•"
            )
            title = item.get("title") or "改进项"
            detail = item.get("detail") or ""
            action = item.get("action") or ""
            lines.append(f"- {badge} **{title}** — {detail}")
            if action:
                lines.append(f"  - 执行：{action}")
        lines.append("")

    skill_items = report.get("skill_learning") or []
    if skill_items:
        lines.extend(["### 🎓 技能学习", ""])
        for item in skill_items:
            title = item.get("title") or "技能"
            summary = item.get("summary") or ""
            action = item.get("action") or ""
            lines.append(f"- **{title}：** {summary}")
            if action:
                lines.append(f"  - 执行：{action}")
        lines.append("")

    research = report.get("skill_research") or []
    ok_research = [r for r in research if r.get("success") and (r.get("summary") or r.get("hits"))]
    if ok_research:
        lines.extend(["### 🔍 外部技能调研", ""])
        for row in ok_research[:3]:
            label = row.get("label") or "调研"
            summary = (row.get("summary") or "")[:180]
            lines.append(f"- **{label}：** {summary}")
        lines.append("")

    if not applied_config and not improvements and not skill_items and not ok_research:
        lines.append("- 本周无额外改进项，维持当前策略与 cron 配置。")
        lines.append("")

    rejected_md = render_rejected_markdown(limit=6)
    if rejected_md:
        lines.append(rejected_md)

    return "\n".join(lines).rstrip() + "\n"


def apply_settings_from_improvements(
    report: dict[str, Any],
    settings: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Apply safe, deterministic settings tweaks suggested by weekly improvements."""
    from agent_reach.daily_run.skill_closure_harness import harness_mode_blocks_settings_writeback

    cfg = deepcopy(settings)
    if harness_mode_blocks_settings_writeback(cfg):
        return cfg, []

    applied: list[str] = []
    improvements = report.get("process_improvements") or []
    mss_applied = exa_applied = schedule_applied = False

    for item in improvements:
        title = str(item.get("title") or "")
        action = str(item.get("action") or "")
        detail = str(item.get("detail") or "")
        category = str(item.get("category") or "")
        blob = f"{title} {action} {detail}".lower()

        if not mss_applied and (
            category == "mss" or "mss" in title.lower() or "预测未命中" in title
        ):
            from agent_reach.daily_run.harness_policy import evolution_mode

            if evolution_mode(cfg, "base_spread") == "fixed":
                mss_cfg = cfg.setdefault("mss_forecast", {})
                old = int(mss_cfg.get("base_spread", 8))
                new = min(old + 1, 15)
                if new != old:
                    mss_cfg["base_spread"] = new
                    applied.append(f"mss_forecast.base_spread: {old} → {new}（{title}）")
            mss_applied = True

        if not exa_applied and category == "data":
            plugins = cfg.setdefault("plugins", {})
            if plugins.get("exa_research_on_close") is not True:
                plugins["exa_research_on_close"] = True
                applied.append("plugins.exa_research_on_close: false → true")
                exa_applied = True
            else:
                exa_applied = True

        if category == "portfolio" and "回撤" in title:
            from agent_reach.daily_run.harness_policy import threshold_mode

            if threshold_mode(cfg, "macro_veto") == "fixed":
                thr = cfg.setdefault("thresholds", {})
                old = int(thr.get("macro_veto", 40))
                new = min(old + 1, 45)
                if new != old:
                    thr["macro_veto"] = new
                    applied.append(f"thresholds.macro_veto: {old} → {new}（{title}）")

        if not schedule_applied and category == "schedule" and item.get("priority") == "high":
            schedule = cfg.setdefault("schedule", {})
            if schedule.get("alert_after_consecutive_failures", 3) > 2:
                schedule["alert_after_consecutive_failures"] = 2
                applied.append("schedule.alert_after_consecutive_failures: 3 → 2（加强任务失败告警）")
            schedule_applied = True

    # De-duplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for note in applied:
        if note not in seen:
            seen.add(note)
            unique.append(note)
    return cfg, unique


def _find_next_h2(text: str, start: int) -> int:
    match_pos = text.find("\n## ", start)
    return len(text) if match_pos < 0 else match_pos + 1


def patch_playbook_in_text(text: str, block: str) -> tuple[str, bool]:
    idx = text.find(PLAYBOOK_PREFIX)
    if idx >= 0:
        end = _find_next_h2(text, idx + len(PLAYBOOK_PREFIX))
        new_text = text[:idx] + block.rstrip() + "\n\n" + text[end:].lstrip()
    elif OPS_HEADER in text:
        new_text = text.replace(OPS_HEADER, block.rstrip() + "\n\n\n" + OPS_HEADER, 1)
    elif EXPERIENCE_HEADER in text:
        pos = text.find(EXPERIENCE_HEADER)
        end = _find_next_h2(text, pos + len(EXPERIENCE_HEADER))
        if end >= len(text):
            new_text = text.rstrip() + "\n\n" + block.rstrip() + "\n"
        else:
            new_text = text[:end].rstrip() + "\n\n" + block.rstrip() + "\n\n" + text[end:].lstrip()
    else:
        new_text = text.rstrip() + "\n\n" + block.rstrip() + "\n"
    return new_text, new_text != text


def patch_playbook_section(path: Path, block: str) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    new_text, changed = patch_playbook_in_text(text, block)
    if not changed:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def canonical_skill_path() -> Path:
    return _repo_root() / "agent_reach" / "skill" / "daily_run_skill.md"


def patch_experience_in_text(
    text: str,
    block: str,
    week_start: str,
    week_end: str,
) -> tuple[str, bool]:
    from agent_reach.daily_run.skill_writeback import (
        _insert_weekly_section,
        _replace_weekly_section,
        week_section_header,
    )

    header = week_section_header(week_start, week_end)
    if header in text:
        new_text = _replace_weekly_section(text, header, block)
    else:
        new_text = _insert_weekly_section(text, block)
    return new_text, new_text != text


def patch_canonical_skill_sections(
    report: dict[str, Any],
    applied_config: list[str],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    week_start = str(report.get("week_start") or "")
    week_end = str(report.get("week_end") or "")
    path = canonical_skill_path()
    if not path.exists():
        return {"canonical": str(path), "experience": False, "playbook": False}

    skill_text = path.read_text(encoding="utf-8")
    normalized = _normalize_report_for_writeback(report, skill_text)
    experience_block = build_weekly_experience_block(normalized)
    playbook_block = build_next_week_playbook_block(normalized, applied_config)
    refinement_id = str(
        report.get("harness_refinement_id") or report.get("refinement_id") or ""
    )

    from agent_reach.daily_run.skill_fragments import (
        FRAGMENTS_DIR,
        external_enabled,
        patch_canonical_stubs,
        write_fragments,
    )

    if external_enabled(settings):
        manifest = write_fragments(
            playbook_block=playbook_block,
            experience_block=experience_block,
            week_start=week_start,
            week_end=week_end,
            refinement_id=refinement_id,
            settings=settings,
        )
        stub_changed = patch_canonical_stubs(path, week_start=week_start, week_end=week_end)
        return {
            "canonical": str(path),
            "experience": True,
            "playbook": True,
            "external": True,
            "stub_changed": stub_changed,
            "normalized_report": normalized,
            "fragments_dir": str(FRAGMENTS_DIR),
            "fragments_manifest": manifest,
        }

    text, exp_changed = patch_experience_in_text(
        skill_text, experience_block, week_start, week_end
    )
    text, pb_changed = patch_playbook_in_text(text, playbook_block)
    if exp_changed or pb_changed:
        path.write_text(text, encoding="utf-8")

    return {
        "canonical": str(path),
        "experience": exp_changed,
        "playbook": pb_changed,
        "external": False,
        "normalized_report": normalized,
    }


def sync_canonical_skill_to_local(settings: Optional[dict[str, Any]] = None) -> list[str]:
    """Copy patched canonical daily_run_skill.md to installed local skill paths."""
    source = canonical_skill_path()
    if not source.exists():
        synced_cursor = sync_cursor_agent_skills_to_local()
        return synced_cursor
    synced: list[str] = []
    for path in resolve_skill_writeback_paths(settings):
        if path.resolve() == source.resolve():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, path)
        synced.append(str(path))
    synced.extend(sync_cursor_agent_skills_to_local())
    return synced


def _collapse_blank_lines(text: str) -> tuple[str, bool]:
    collapsed = re.sub(r"\n{4,}", "\n\n\n", text)
    return collapsed, collapsed != text


def _remove_orphan_fragments(text: str) -> tuple[str, bool]:
    """Drop corrupted list fragments between --- without a heading."""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    changed = False
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---" and i + 1 < len(lines):
            nxt = lines[i + 1].lstrip()
            if nxt.startswith("*") and not lines[i + 1].startswith("#"):
                j = i + 1
                while j < len(lines) and not lines[j].startswith("## ") and lines[j].strip() != "---":
                    j += 1
                    changed = True
                i = j
                continue
        out.append(line)
        i += 1
    return "\n".join(out), changed


def _dedupe_weekly_review_blocks(text: str) -> tuple[str, bool]:
    """Keep only the first weekly review block for each week range header."""
    marker = "### 📅 "
    if marker not in text:
        return text, False
    parts = text.split(marker)
    if len(parts) <= 1:
        return text, False
    kept: list[str] = [parts[0]]
    seen: set[str] = set()
    changed = False
    for chunk in parts[1:]:
        header_line = chunk.split("\n", 1)[0]
        key = header_line.strip()
        if "周复盘（周六自动沉淀）" not in key:
            kept.append(marker + chunk)
            continue
        if key in seen:
            changed = True
            continue
        seen.add(key)
        kept.append(marker + chunk)
    return marker.join(kept), changed


def _dedupe_duplicate_h2_sections(text: str) -> tuple[str, bool]:
    """Remove repeated top-level ## sections (keep first occurrence)."""
    chunks = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    if len(chunks) <= 1:
        return text, False
    out: list[str] = [chunks[0]]
    seen: set[str] = set()
    changed = False
    for chunk in chunks[1:]:
        title = chunk.split("\n", 1)[0].strip()
        if title in seen:
            changed = True
            continue
        seen.add(title)
        out.append(chunk)
    return "".join(out), changed


def optimize_skill_markdown(text: str, *, settings: Optional[dict[str, Any]] = None) -> tuple[str, list[str]]:
    """Structural cleanup after weekly writeback (dedupe, orphans, whitespace, archive)."""
    fixes: list[str] = []
    for fn, label in (
        (_collapse_blank_lines, "collapse_blank_lines"),
        (_remove_orphan_fragments, "remove_orphan_fragments"),
        (_dedupe_weekly_review_blocks, "dedupe_weekly_reviews"),
        (_dedupe_duplicate_h2_sections, "dedupe_h2_sections"),
    ):
        text, changed = fn(text)
        if changed:
            fixes.append(label)
    text, archived = compact_experience_sections(text, settings=settings)
    if archived:
        fixes.append(f"archive_experience_{len(archived)}")
    return text.rstrip() + "\n", fixes


def audit_weekly_skill(
    settings: Optional[dict[str, Any]] = None,
    *,
    report: Optional[dict[str, Any]] = None,
    applied_config: Optional[list[str]] = None,
    skip_sync: bool = False,
) -> dict[str, Any]:
    """Final Saturday step: validate skill structure, optimize, re-sync locally."""
    path = canonical_skill_path()
    if not path.exists():
        return {"ok": False, "reason": "canonical skill missing", "path": str(path)}

    raw = path.read_text(encoding="utf-8")
    missing = [sec for sec in REQUIRED_SKILL_SECTIONS if sec not in raw]
    optimized, fixes = optimize_skill_markdown(raw, settings=settings)
    synced: list[str] = []
    if fixes or optimized != raw:
        path.write_text(optimized, encoding="utf-8")
    if (
        not skip_sync
        and (settings is None or (settings.get("weekly_report") or {}).get("skill_sync_local", True) is not False)
    ):
        synced = sync_canonical_skill_to_local(settings)

    result: dict[str, Any] = {
        "ok": not missing,
        "path": str(path),
        "missing_sections": missing,
        "fixes": fixes,
        "lines_before": len(raw.splitlines()),
        "lines_after": len(optimized.splitlines()),
        "synced_skills": synced,
        "supersession": audit_supersession_harness(report) if report else {},
    }

    if report:
        from agent_reach.daily_run.skill_gates import run_skill_gates

        gates = run_skill_gates(
            optimized,
            report,
            applied_config=applied_config or [],
            settings=settings,
        )
        result["gates"] = gates
        if gates.get("ok") is False and not gates.get("skipped"):
            result["ok"] = False
            try:
                from agent_reach.daily_run.skill_gates_harness import apply_skill_gates_harness_refinement

                result["skill_gates_harness"] = apply_skill_gates_harness_refinement(
                    gates,
                    settings=settings,
                )
            except Exception:
                pass

    return result


def ensure_runtime_updated() -> dict[str, Any]:
    """Reinstall editable package so cron uses latest code next week."""
    repo = _repo_root()
    result: dict[str, Any] = {"repo": str(repo), "steps": [], "errors": []}
    stamp_path = Path.home() / ".agent-reach" / "daily_run" / "runtime_install.stamp"
    pyproject = repo / "pyproject.toml"
    pkg_dir = repo / "agent_reach"
    try:
        marker = f"{pyproject.stat().st_mtime_ns}:{pkg_dir.stat().st_mtime_ns}"
    except OSError:
        marker = ""
    if marker and stamp_path.exists() and stamp_path.read_text(encoding="utf-8").strip() == marker:
        result["steps"].append("pip_skipped_unchanged")
        clear_settings_cache()
        result["steps"].append("settings_cache_cleared")
        return result

    cmd = [sys.executable, "-m", "pip", "install", "-q", "-e", f"{repo}[dev]"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=str(repo))
        if proc.returncode == 0:
            result["steps"].append("pip_install_editable")
            if marker:
                stamp_path.parent.mkdir(parents=True, exist_ok=True)
                stamp_path.write_text(marker + "\n", encoding="utf-8")
        else:
            result["errors"].append((proc.stderr or proc.stdout or "pip failed").strip()[:500])
    except OSError as exc:
        result["errors"].append(str(exc))
    clear_settings_cache()
    result["steps"].append("settings_cache_cleared")
    return result


def save_playbook_manifest(
    report: dict[str, Any],
    applied_config: list[str],
    synced_skills: list[str],
    runtime: dict[str, Any],
    skill_audit: Optional[dict[str, Any]] = None,
    *,
    harness_refinement_id: str = "",
) -> Path:
    PLAYBOOK_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "week_start": report.get("week_start"),
        "week_end": report.get("week_end"),
        "harness_refinement_id": harness_refinement_id or report.get("harness_refinement_id") or "",
        "applied_config": applied_config,
        "process_improvements": report.get("process_improvements") or [],
        "skill_learning": report.get("skill_learning") or [],
        "synced_skills": synced_skills,
        "runtime": runtime,
        "skill_audit": skill_audit or {},
    }
    PLAYBOOK_MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return PLAYBOOK_MANIFEST


def append_skill_changelog(event: dict[str, Any]) -> None:
    SKILL_CHANGELOG.parent.mkdir(parents=True, exist_ok=True)
    row = {"at": datetime.now(timezone.utc).isoformat(), **event}
    with open(SKILL_CHANGELOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def annotate_weekly_harness_audit(
    *,
    week_start: str,
    week_end: str,
    refinement_id: str,
    settings: Optional[dict[str, Any]] = None,
    skip_sync: bool = False,
) -> dict[str, Any]:
    """Post-harness: stamp refinement_id into skill experience + playbook manifest."""
    if not refinement_id:
        return {"skipped": True, "reason": "no refinement_id"}

    path = canonical_skill_path()
    if not path.exists():
        return {"skipped": True, "reason": "canonical skill missing"}

    text = path.read_text(encoding="utf-8")
    new_text = annotate_experience_refinement_id(
        text,
        week_start=week_start,
        week_end=week_end,
        refinement_id=refinement_id,
    )
    changed = new_text != text
    if changed:
        path.write_text(new_text, encoding="utf-8")

    from agent_reach.daily_run.skill_fragments import annotate_experience_fragment, external_enabled

    fragment_changed = False
    if external_enabled(settings):
        fragment_changed = annotate_experience_fragment(
            week_start=week_start,
            week_end=week_end,
            refinement_id=refinement_id,
        )

    if (changed or fragment_changed) and not skip_sync:
        sync_canonical_skill_to_local(settings)

    if PLAYBOOK_MANIFEST.exists():
        try:
            manifest = json.loads(PLAYBOOK_MANIFEST.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {}
        manifest["harness_refinement_id"] = refinement_id
        manifest["harness_annotated_at"] = datetime.now(timezone.utc).isoformat()
        PLAYBOOK_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    append_skill_changelog(
        {
            "action": "harness_annotate",
            "week_start": week_start,
            "week_end": week_end,
            "refinement_id": refinement_id,
            "skill_changed": changed,
        }
    )
    return {"skipped": False, "refinement_id": refinement_id, "skill_changed": changed, "fragment_changed": fragment_changed}


def apply_weekly_skill_closure(
    report: dict[str, Any],
    settings: Optional[dict[str, Any]] = None,
    *,
    harness_refinement_id: str = "",
) -> dict[str, Any]:
    """Write weekly learnings to skill, apply safe settings fixes, sync local runtime."""
    cfg = settings or load_settings()
    weekly_cfg = cfg.get("weekly_report") or {}
    if weekly_cfg.get("skill_writeback", True) is False:
        return {"skipped": True, "reason": "skill_writeback disabled"}

    week_start = str(report.get("week_start") or "")
    week_end = str(report.get("week_end") or "")
    if not week_start or not week_end:
        return {"skipped": True, "reason": "missing week range"}

    if harness_refinement_id:
        report = dict(report)
        report["harness_refinement_id"] = harness_refinement_id
        report["refinement_id"] = harness_refinement_id

    skill_harness_ref: dict[str, Any] = {}
    try:
        from agent_reach.daily_run.skill_closure_harness import apply_skill_closure_harness_refinement

        skill_harness_ref = apply_skill_closure_harness_refinement(report, settings=cfg)
    except Exception:
        skill_harness_ref = {"skipped": True, "reason": "skill_closure_harness error"}

    new_settings, applied_config = apply_settings_from_improvements(report, cfg)
    settings_path: Optional[str] = None
    if applied_config and weekly_cfg.get("skill_auto_apply_settings", True) is not False:
        settings_path = str(save_user_settings(new_settings))

    patch_result = patch_canonical_skill_sections(report, applied_config, settings=new_settings)
    normalized_report = patch_result.get("normalized_report") or report

    runtime: dict[str, Any] = {}
    if weekly_cfg.get("skill_sync_runtime", True) is not False:
        runtime = ensure_runtime_updated()

    skill_audit: dict[str, Any] = {}
    if weekly_cfg.get("skill_audit", True) is not False:
        skill_audit = audit_weekly_skill(
            new_settings,
            report=normalized_report,
            applied_config=applied_config,
            skip_sync=True,
        )

    synced: list[str] = []
    if weekly_cfg.get("skill_sync_local", True) is not False:
        synced = sync_canonical_skill_to_local(new_settings)

    manifest_path = save_playbook_manifest(
        report,
        applied_config,
        synced,
        runtime,
        skill_audit=skill_audit,
        harness_refinement_id=str(report.get("harness_refinement_id") or ""),
    )
    append_skill_changelog(
        {
            "action": "weekly_writeback",
            "week_start": week_start,
            "week_end": week_end,
            "applied_config": applied_config,
            "manifest_path": str(manifest_path),
            "rejected_blocked": report.get("_rejected_blocked") or [],
            "supersession": (skill_audit.get("supersession") or {}),
        }
    )

    return {
        "skipped": False,
        "week_start": week_start,
        "week_end": week_end,
        "applied_config": applied_config,
        "settings_path": settings_path,
        "patch": patch_result,
        "synced_skills": synced,
        "runtime": runtime,
        "skill_audit": skill_audit,
        "manifest_path": str(manifest_path),
        "skill_harness_refinement": skill_harness_ref,
    }


def write_weekly_skill_experience(
    report: dict[str, Any],
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Backward-compatible entry: full weekly skill closure."""
    return apply_weekly_skill_closure(report, settings)

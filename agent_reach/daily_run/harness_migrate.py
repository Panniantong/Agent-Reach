# -*- coding: utf-8
"""Strip evolved keys from static daily_run_settings when harness mode is active."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.harness_policy import (
    EVOLVED_CONFIG_KEYS_BY_SECTION,
    EVOLVED_TOP_LEVEL_KEYS,
    harness_evolution_mode,
    list_static_config_pollution,
)
from agent_reach.daily_run.settings import load_settings, save_user_settings, user_settings_path


def strip_evolved_keys(settings: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return cleaned copy and list of removed dotted keys."""
    if harness_evolution_mode(settings) != "harness":
        return deepcopy(settings), []

    cleaned = deepcopy(settings)
    removed: list[str] = []

    for section, keys in EVOLVED_CONFIG_KEYS_BY_SECTION.items():
        block = cleaned.get(section)
        if not isinstance(block, dict):
            continue
        for key in keys:
            if key in block:
                del block[key]
                removed.append(f"{section}.{key}")

    for key in EVOLVED_TOP_LEVEL_KEYS:
        if key in cleaned:
            del cleaned[key]
            removed.append(key)

    return cleaned, removed


HARNESS_SYNC_KEYS: tuple[str, ...] = (
    "push_summary_on_close",
    "push_summary_on_weekly",
    "push_summary_on_forecast",
    "push_summary_on_morning",
    "push_summary_on_intraday",
    "push_harness_errors_on_feishu",
    "push_rollback_on_feishu",
    "auto_rollback_on_bad_trade",
    "bad_trade_pnl_pct",
    "bad_trade_weekly_pnl_pct",
)


HARNESS_APPLY_GATE_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "block_policy_on_audit_fail": True,
    "block_policy_on_structured_incomplete": True,
    "block_playbook_on_morning_gate_fail": True,
}

HARNESS_INJECTION_DEFAULTS: dict[str, Any] = {
    "max_per_kind_per_job": 8,
    "max_chars_per_line": 240,
    "max_overlay_claims": 3,
    "max_overlay_chars": 1200,
    "enforce_claim_decisions": True,
}

HARNESS_SNAPSHOT_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "max_keep": 20,
}

HARNESS_LAYER_B_ADMISSION_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "max_edits": 8,
    "max_score_drift": 15,
    "max_ratio_drift": 0.25,
    "block_threshold_literals": True,
}

HARNESS_FORGE_GATES_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "pnl_target": {
        "max_target_pct": 3.0,
        "max_target_cny": 50000,
    },
    "forecast_calibrate": {
        "use_week_forecast_bounds": True,
    },
}

HARNESS_WEEKLY_NARRATIVE_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "append_to_weekly_card": True,
    "audit_days": 7,
}

HARNESS_CONTEXT_DOCTOR_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "similarity_threshold": 0.86,
    "min_chars": 12,
    "detect_conflicts": True,
}

HARNESS_RIGOR_SCHEMA_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "jobs": ["optimize"],
    "min_trials": 1,
    "require_metrics": ["total_return", "max_drawdown"],
}

HARNESS_BRANCH_OVERLAY_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "use_root_for_main": True,
    "main_names": ["main", "master"],
}

HARNESS_STUDY_REGISTRY_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "max_entries": 200,
    "jobs": ["optimize", "backtest"],
}

HARNESS_RIGOR_CHECK_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "block_on_fail": {"optimize": True},
    "jobs": {
        "finance_close": True,
        "finance_ledger": True,
        "finance_ledger_prep": True,
        "finance_variance": True,
        "finance_close_plan": True,
        "finance_statements": True,
        "finance_research": True,
        "expert_consensus": True,
        "expert_consensus_weekly": True,
        "optimize": True,
        "pnl_target": True,
        "forecast_calibrate": True,
    },
}


def sync_user_harness_keys(
    *,
    path: Optional[Path] = None,
    settings: Optional[dict[str, Any]] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Merge missing harness keys from repo defaults into user settings."""
    from agent_reach.daily_run.settings import _DEFAULT_PATH, _read_json, save_user_settings, user_settings_path

    target = path or user_settings_path()
    current = settings or (_read_json(target) if target.exists() else load_settings())
    defaults = _read_json(_DEFAULT_PATH) if _DEFAULT_PATH.exists() else {}
    default_harness = dict(defaults.get("harness") or {})
    harness = dict(current.get("harness") or {})
    added: list[str] = []

    for key in HARNESS_SYNC_KEYS:
        if key not in harness and key in default_harness:
            harness[key] = deepcopy(default_harness[key])
            added.append(f"harness.{key}")

    for nested_key, nested_defaults in (
        ("apply_gate", HARNESS_APPLY_GATE_DEFAULTS),
        ("injection", HARNESS_INJECTION_DEFAULTS),
        ("snapshots", HARNESS_SNAPSHOT_DEFAULTS),
        ("layer_b_admission", HARNESS_LAYER_B_ADMISSION_DEFAULTS),
        ("forge_gates", HARNESS_FORGE_GATES_DEFAULTS),
        ("weekly_narrative", HARNESS_WEEKLY_NARRATIVE_DEFAULTS),
        ("context_doctor", HARNESS_CONTEXT_DOCTOR_DEFAULTS),
        ("rigor_schema", HARNESS_RIGOR_SCHEMA_DEFAULTS),
        ("branch_overlay", HARNESS_BRANCH_OVERLAY_DEFAULTS),
        ("study_registry", HARNESS_STUDY_REGISTRY_DEFAULTS),
        ("rigor_check", HARNESS_RIGOR_CHECK_DEFAULTS),
    ):
        block = dict(harness.get(nested_key) or {})
        default_block = dict(default_harness.get(nested_key) or nested_defaults)
        for sub_key, sub_val in default_block.items():
            if sub_key not in block:
                block[sub_key] = deepcopy(sub_val)
                added.append(f"harness.{nested_key}.{sub_key}")
        if block:
            harness[nested_key] = block

    default_jobs = dict(default_harness.get("jobs") or {})
    jobs = dict(harness.get("jobs") or {})
    for job_key, job_val in default_jobs.items():
        if job_key not in jobs:
            jobs[job_key] = deepcopy(job_val)
            added.append(f"harness.jobs.{job_key}")
    if jobs:
        harness["jobs"] = jobs

    for section_key in ("expert_consensus",):
        default_section = dict(defaults.get(section_key) or {})
        section = dict(current.get(section_key) or {})
        for sub_key, sub_val in default_section.items():
            if sub_key not in section:
                section[sub_key] = deepcopy(sub_val)
                added.append(f"{section_key}.{sub_key}")
        if section:
            current[section_key] = section

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "path": str(target),
        "added": added,
        "saved": False,
    }
    if not added:
        result["message"] = "无需同步（harness 键已齐全）"
        return result

    if dry_run:
        result["message"] = f"将新增 {len(added)} 个 harness 键"
        return result

    merged = deepcopy(current)
    merged["harness"] = harness
    if "expert_consensus" in current:
        merged["expert_consensus"] = current["expert_consensus"]
    save_user_settings(merged, path=target)
    result["saved"] = True
    result["message"] = f"已新增 {len(added)} 个 harness 键"
    return result


def render_sync_harness_markdown(result: dict[str, Any]) -> str:
    lines = [
        "**Harness 配置同步**",
        "",
        f"- 路径：`{result.get('path')}`",
        f"- 状态：{result.get('message')}",
    ]
    added = result.get("added") or []
    if added:
        lines.extend(["", "**新增键：**", ""])
        for key in added:
            lines.append(f"- `{key}`")
    return "\n".join(lines)


def migrate_user_settings(
    *,
    path: Optional[Path] = None,
    settings: Optional[dict[str, Any]] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Remove static evolved keys from user settings file."""
    src = settings or load_settings()
    target = path or user_settings_path()
    pollution = list_static_config_pollution(src)
    cleaned, removed = strip_evolved_keys(src)

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "path": str(target),
        "harness_mode": harness_evolution_mode(src) == "harness",
        "pollution_detected": pollution,
        "removed": removed,
        "saved": False,
    }

    if not removed:
        result["message"] = "无需迁移（无 evolved keys 或 harness 未启用）"
        return result

    if dry_run:
        result["message"] = f"将移除 {len(removed)} 个 evolved keys"
        return result

    save_user_settings(cleaned, path=target)
    result["saved"] = True
    result["message"] = f"已移除 {len(removed)} 个 evolved keys"
    return result


def render_migrate_markdown(result: dict[str, Any]) -> str:
    lines = [
        "**Harness 静态配置迁移**",
        "",
        f"- 模式：{'harness' if result.get('harness_mode') else 'fixed'}",
        f"- 路径：`{result.get('path')}`",
        f"- 状态：{result.get('message')}",
    ]
    removed = result.get("removed") or []
    if removed:
        lines.extend(["", "**移除键：**", ""])
        for key in removed:
            lines.append(f"- `{key}`")
    return "\n".join(lines)

# -*- coding: utf-8
"""One-click enable Team-First workflow in user daily_run settings."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.settings import (
    _DEFAULT_PATH,
    _merge_repo_defaults,
    _read_json,
    load_settings,
    save_user_settings,
    user_settings_path,
)

TEAM_FIRST_PATCH: dict[str, Any] = {
    "enabled": True,
    "parallel": True,
    "supervisor": True,
    "mode": "full_parallel",
    "mss_experts": True,
    "morning_mss_experts": True,
    "intraday_mss_experts": True,
    "close_mss_experts": True,
    "morning_team_first": True,
    "close_team_first": True,
    "intraday_team_first": True,
    "intraday_experts": True,
    "counter_thesis_downgrade": True,
}


def enable_team_first(
    *,
    path: Optional[Path] = None,
    settings: Optional[dict[str, Any]] = None,
    morning_team_first: bool = True,
    close_team_first: bool = True,
    intraday_team_first: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Merge Team-First flags into ~/.agent-reach/daily_run_settings.json."""
    target = path or user_settings_path()
    base = settings or (load_settings() if target.exists() or not _DEFAULT_PATH.exists() else _read_json(_DEFAULT_PATH))
    if target.exists() and settings is None:
        user = _read_json(target)
        merged = _merge_repo_defaults(user, target)
    else:
        merged = deepcopy(base)

    team = dict(merged.get("team") or {})
    before = deepcopy(team)
    patch = dict(TEAM_FIRST_PATCH)
    patch["morning_team_first"] = bool(morning_team_first)
    patch["close_team_first"] = bool(close_team_first)
    patch["intraday_team_first"] = bool(intraday_team_first)
    patch["intraday_experts"] = True
    team.update(patch)
    merged["team"] = team

    changed: list[str] = []
    for key, value in patch.items():
        if before.get(key) != value:
            changed.append(f"team.{key}={value!r}")

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "path": str(target),
        "changed": changed,
        "team": team,
        "saved": False,
    }
    if not changed:
        result["message"] = "Team-First 已启用，无需变更"
        return result

    if dry_run:
        result["message"] = f"将更新 {len(changed)} 个 team 键"
        return result

    save_user_settings(merged, path=target)
    result["saved"] = True
    result["message"] = f"已启用 Team-First（{len(changed)} 项）"
    return result


def render_team_setup_markdown(result: dict[str, Any]) -> str:
    lines = [
        "**Team-First 一键启用**",
        "",
        f"- 路径：`{result.get('path')}`",
        f"- 状态：{result.get('message')}",
    ]
    changed = result.get("changed") or []
    if changed:
        lines.extend(["", "**变更：**", ""])
        for key in changed:
            lines.append(f"- `{key}`")
    team = result.get("team") or {}
    if team:
        lines.extend(
            [
                "",
                f"- team.enabled={team.get('enabled')}",
                f"- morning_team_first={team.get('morning_team_first')}",
                f"- close_team_first={team.get('close_team_first')}",
                f"- intraday_team_first={team.get('intraday_team_first')}",
            ]
        )
    return "\n".join(lines)

# -*- coding: utf-8
"""Daily-run operational diagnostics for agent-reach doctor."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.intent_cache import intent_cache_dir, intent_config
from agent_reach.daily_run.redfox_gzh import list_gzh_subscriptions
from agent_reach.daily_run.settings import load_settings
from agent_reach.daily_run.team import experts_enabled, mss_experts_enabled, team_first_enabled


def collect_daily_run_diagnostics(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = settings or load_settings()
    team_cfg = cfg.get("team") or {}
    intent_cfg = intent_config(cfg)

    workflows: dict[str, dict[str, bool]] = {}
    for wf in ("morning", "close", "intraday"):
        workflows[wf] = {
            "team_first": team_first_enabled(cfg, workflow=wf),
            "experts": experts_enabled(cfg, workflow=wf),
            "mss_experts": mss_experts_enabled(cfg, workflow=wf),
        }

    cache_dir = intent_cache_dir()
    cache_files: list[Path] = []
    if cache_dir.exists():
        cache_files = [p for p in cache_dir.glob("*.json") if p.name != "rate_window.json"]

    rate_recent = 0
    rate_path = cache_dir / "rate_window.json"
    if rate_path.exists():
        try:
            data = json.loads(rate_path.read_text(encoding="utf-8"))
            window = intent_cfg["rate_limit_window_seconds"]
            now = time.time()
            rate_recent = sum(
                1 for t in (data.get("timestamps") or []) if now - float(t) < window
            )
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            rate_recent = 0

    gzh = list_gzh_subscriptions(settings=cfg)
    gzh_total = len(gzh.get("official") or []) + len(gzh.get("personal") or [])

    team_on = team_cfg.get("enabled") is True
    any_team_first = any(row.get("team_first") for row in workflows.values())
    status = "ok"
    if not team_on:
        status = "warn"
    elif team_on and not any_team_first:
        status = "warn"

    message_parts = [
        f"Team.enabled={team_on}",
        f"intent_cache={len(cache_files)} entries",
        f"rate_window={rate_recent}/{intent_cfg['rate_limit_max']}",
        f"gzh={gzh_total} subs",
    ]

    return {
        "status": status,
        "message": " · ".join(message_parts),
        "team": {
            "enabled": team_on,
            "mode": team_cfg.get("mode", "full_parallel"),
            "workflows": workflows,
        },
        "intent_cache": {
            "enabled": intent_cfg["enabled"],
            "entries": len(cache_files),
            "rate_limit_max": intent_cfg["rate_limit_max"],
            "rate_limit_window_seconds": intent_cfg["rate_limit_window_seconds"],
            "rate_window_usage": rate_recent,
            "cache_dir": str(cache_dir),
        },
        "gzh_subscriptions": {
            "path": gzh.get("path"),
            "official": len(gzh.get("official") or []),
            "personal": len(gzh.get("personal") or []),
        },
        "plugins": {
            "pipeline_enabled": (cfg.get("plugins") or {}).get("pipeline_enabled", True) is not False,
            "filters": list((cfg.get("plugins") or {}).get("filters") or []),
        },
    }


def format_daily_run_diagnostics_markdown(diag: dict[str, Any]) -> str:
    lines = ["", "[bold]Daily-run 诊断：[/bold]"]
    status = diag.get("status", "warn")
    icon = "✅" if status == "ok" else "[!]"
    lines.append(f"  {icon} {diag.get('message', '')}")

    team = diag.get("team") or {}
    lines.append(f"  Team 模式：[dim]{team.get('mode', 'full_parallel')}[/dim]")
    for wf, row in (team.get("workflows") or {}).items():
        lines.append(
            f"  - {wf}: team_first={row.get('team_first')} · "
            f"experts={row.get('experts')} · mss={row.get('mss_experts')}"
        )

    intent = diag.get("intent_cache") or {}
    lines.append(
        f"  Intent 缓存：{intent.get('entries', 0)} 条 · "
        f"限流 {intent.get('rate_window_usage', 0)}/{intent.get('rate_limit_max', 0)} "
        f"（{intent.get('rate_limit_window_seconds', 0)}s 窗口）"
    )

    gzh = diag.get("gzh_subscriptions") or {}
    lines.append(
        f"  GZH 订阅：官方 {gzh.get('official', 0)} · 个人 {gzh.get('personal', 0)}"
    )

    plugins = diag.get("plugins") or {}
    filters = plugins.get("filters") or []
    if filters:
        lines.append(f"  预专家 filters：{', '.join(filters)}")
    return "\n".join(lines)

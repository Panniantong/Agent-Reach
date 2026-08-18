# -*- coding: utf-8
"""Rolling pre-apply snapshots for harness state (dsh-guard style)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.harness import HarnessState, _state_path, harness_dir, load_harness, save_harness


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def snapshot_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if settings is None:
        try:
            from agent_reach.daily_run.settings import load_settings

            settings = load_settings()
        except Exception:
            settings = {}
    raw = dict((settings.get("harness") or {}).get("snapshots") or {})
    return {
        "enabled": raw.get("enabled", True) is not False,
        "max_keep": max(3, int(raw.get("max_keep") or 20)),
    }


def snapshots_dir() -> Path:
    return harness_dir() / "snapshots"


def save_pre_apply_snapshot(
    state: HarnessState,
    *,
    job: str,
    trigger: str = "refine",
    settings: Optional[dict[str, Any]] = None,
) -> Optional[Path]:
    """Persist harness state before applying edits."""
    cfg = snapshot_cfg(settings)
    if not cfg["enabled"]:
        return None

    out_dir = snapshots_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    safe_job = "".join(c if c.isalnum() or c in "-_" else "_" for c in job)[:32]
    path = out_dir / f"{stamp}_{safe_job}_{trigger}.json"
    payload = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "job": job,
        "trigger": trigger,
        "state": {
            "schema": state.schema,
            "entries": {
                kind: {eid: entry.to_dict() for eid, entry in bucket.items()}
                for kind, bucket in state.entries.items()
            },
            "refinements": [event.to_dict() for event in state.refinements[-200:]],
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _rotate_snapshots(cfg["max_keep"])
    return path


def _rotate_snapshots(max_keep: int) -> None:
    out_dir = snapshots_dir()
    if not out_dir.exists():
        return
    files = sorted(out_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[max_keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def list_snapshots(*, limit: int = 10) -> list[dict[str, Any]]:
    out_dir = snapshots_dir()
    if not out_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(out_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        rows.append(
            {
                "path": str(path),
                "name": path.name,
                "saved_at": data.get("saved_at"),
                "job": data.get("job"),
                "trigger": data.get("trigger"),
            }
        )
    return rows


def restore_snapshot(path: str | Path) -> dict[str, Any]:
    """Restore harness_state.json from a snapshot file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"snapshot not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    block = data.get("state")
    if not isinstance(block, dict):
        raise ValueError("invalid snapshot payload")

    target = _state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = save_pre_apply_snapshot(load_harness(), job="restore", trigger="pre_restore")
    target.write_text(json.dumps(block, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "restored_from": str(p),
        "pre_restore_snapshot": str(backup) if backup else None,
        "state_path": str(target),
    }

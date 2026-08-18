# -*- coding: utf-8
"""Git branch-aware harness paths (dsh-memory-evolve style isolation)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Optional


def _harness_root() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "harness"


def branch_overlay_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    harness = dict((settings or {}).get("harness") or {})
    raw = dict(harness.get("branch_overlay") or {})
    return {
        "enabled": raw.get("enabled", True) is not False,
        "use_root_for_main": raw.get("use_root_for_main", True) is not False,
        "main_names": {str(x).lower() for x in (raw.get("main_names") or ["main", "master"])},
    }


def detect_git_branch(*, cwd: Optional[Path] = None) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(cwd or Path.cwd()),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        branch = (proc.stdout or "").strip()
        if proc.returncode == 0 and branch and branch != "HEAD":
            return branch
    except (OSError, subprocess.SubprocessError):
        pass
    return "detached"


def branch_slug(branch: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(branch or "detached")).strip("-")
    return slug[:80] or "detached"


def resolve_harness_paths(settings: Optional[dict[str, Any]] = None) -> dict[str, Path]:
    cfg = branch_overlay_cfg(settings)
    root = _harness_root()
    branch = detect_git_branch()
    if not cfg["enabled"] or (cfg["use_root_for_main"] and branch.lower() in cfg["main_names"]):
        base = root
    else:
        base = root / "branches" / branch_slug(branch)
    base.mkdir(parents=True, exist_ok=True)
    return {
        "root": base,
        "branch": branch,
        "state": base / "harness_state.json",
        "refinements": base / "refinements.jsonl",
        "snapshots": base / "snapshots",
        "registry": base / "study_registry.json",
        "audit": root / "apply_audit.jsonl",
    }


def resolve_harness_state_path(settings: Optional[dict[str, Any]] = None) -> Path:
    return resolve_harness_paths(settings)["state"]

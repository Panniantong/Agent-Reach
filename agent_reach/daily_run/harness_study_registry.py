# -*- coding: utf-8
"""RigorQuant-style study registry for optimize/backtest trials."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4


def _registry_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    harness = dict((settings or {}).get("harness") or {})
    raw = dict(harness.get("study_registry") or {})
    return {
        "enabled": raw.get("enabled", True) is not False,
        "max_entries": max(10, int(raw.get("max_entries") or 200)),
        "jobs": set(raw.get("jobs") or ["optimize", "backtest"]),
    }


def _registry_path(settings: Optional[dict[str, Any]] = None) -> Path:
    from agent_reach.daily_run.harness_git import resolve_harness_paths

    paths = resolve_harness_paths(settings)
    return paths["registry"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StudyRegistryEntry:
    study_id: str
    job: str
    at: str
    git_branch: str = ""
    objective: str = ""
    best_score: Optional[float] = None
    trials: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    best_params: dict[str, Any] = field(default_factory=dict)
    refinement_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "job": self.job,
            "at": self.at,
            "git_branch": self.git_branch,
            "objective": self.objective,
            "best_score": self.best_score,
            "trials": self.trials,
            "metrics": dict(self.metrics),
            "best_params": dict(self.best_params),
            "refinement_id": self.refinement_id,
        }


def load_study_registry(*, settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    path = _registry_path(settings)
    if not path.exists():
        return {"schema": 1, "studies": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"schema": 1, "studies": []}
    if not isinstance(data, dict):
        return {"schema": 1, "studies": []}
    data.setdefault("schema", 1)
    data.setdefault("studies", [])
    return data


def save_study_registry(data: dict[str, Any], *, settings: Optional[dict[str, Any]] = None) -> Path:
    path = _registry_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def register_study(
    job: str,
    domain: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    refinement_id: str = "",
) -> Optional[dict[str, Any]]:
    cfg = _registry_cfg(settings)
    if not cfg["enabled"] or job not in cfg["jobs"]:
        return None

    from agent_reach.daily_run.harness_git import detect_git_branch

    entry = StudyRegistryEntry(
        study_id=f"study_{uuid4().hex[:10]}",
        job=job,
        at=_now_iso(),
        git_branch=detect_git_branch(),
        objective=str(domain.get("objective") or ""),
        best_score=float(domain["best_score"]) if domain.get("best_score") is not None else None,
        trials=int(domain.get("trials") or 0),
        metrics=dict(domain.get("metrics") or {}),
        best_params=dict(domain.get("best_params") or {}),
        refinement_id=refinement_id,
    )
    data = load_study_registry(settings=settings)
    studies = list(data.get("studies") or [])
    studies.append(entry.to_dict())
    data["studies"] = studies[-cfg["max_entries"] :]
    data["updated_at"] = _now_iso()
    save_study_registry(data, settings=settings)
    return entry.to_dict()


def list_studies_in_window(
    *,
    week_start: Optional[str] = None,
    week_end: Optional[str] = None,
    settings: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    from agent_reach.daily_run.harness_weekly_narrative import _parse_iso_day

    data = load_study_registry(settings=settings)
    start = _parse_iso_day(week_start or "")
    end = _parse_iso_day(week_end or "")
    out: list[dict[str, Any]] = []
    for row in data.get("studies") or []:
        day = _parse_iso_day(str(row.get("at") or ""))
        if start and end and day is not None and (day < start or day > end):
            continue
        out.append(row)
    return out

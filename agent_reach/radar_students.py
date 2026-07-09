# -*- coding: utf-8 -*-
"""Student roster for the mentor-student pipeline.

Multiple local (Ollama) students each draft the daily brief; the mentor
panel scores every draft per-student, so the roster accumulates a track
record. Students are swappable on purpose — when a stronger open-source
small model lands (new qwen, nemotron, ...), `ollama pull` it and
`agent-reach radar-students add` it; retire laggards once their rolling
mean proves it. Retirement is suggested automatically but ALWAYS human-
confirmed (sampling noise kills good students otherwise).

Roster lives in ``~/.agent-reach/radar/training/students.yaml``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from loguru import logger

from agent_reach.radar import RADAR_DIR

STUDENTS_FILE = RADAR_DIR / "training" / "students.yaml"

# Two qwen3:4b personas to start — same weights, different reading angle,
# so drafts diverge enough for the mentor panel to pick a winner.
DEFAULT_STUDENTS = [
    {
        "id": "qwen3-4b-macro",
        "model": "qwen3:4b",
        "persona": "宏觀敘事型：優先串聯因果與大局，先講「為什麼重要」再講細節",
        "options": {"temperature": 0.3, "seed": 7},
        "status": "active",
    },
    {
        "id": "qwen3-4b-supply",
        "model": "qwen3:4b",
        "persona": "供應鏈數字型：緊扣數字、產能、報價與交期，觀點必附出處",
        "options": {"temperature": 0.5, "seed": 42},
        "status": "active",
    },
]


def load_students(path: Optional[Path] = None) -> list[dict]:
    """Load the roster, seeding the default file on first run."""
    p = Path(path) if path else STUDENTS_FILE
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
        return data if isinstance(data, list) else []
    students = [dict(s, added=f"{datetime.now(timezone.utc):%Y-%m-%d}") for s in DEFAULT_STUDENTS]
    save_students(students, p)
    logger.info(f"Seeded default student roster at {p}")
    return students


def save_students(students: list[dict], path: Optional[Path] = None) -> None:
    p = Path(path) if path else STUDENTS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        yaml.dump(students, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def active_students(students: list[dict]) -> list[dict]:
    return [s for s in students if s.get("status", "active") == "active"]


def add_student(
    student_id: str,
    model: str,
    persona: str = "",
    temperature: float = 0.3,
    seed: Optional[int] = None,
    path: Optional[Path] = None,
) -> list[dict]:
    """Add a new student (e.g. a freshly pulled HF/Ollama model)."""
    students = load_students(path)
    if any(s.get("id") == student_id for s in students):
        raise ValueError(f"student id already exists: {student_id}")
    options: dict = {"temperature": temperature}
    if seed is not None:
        options["seed"] = seed
    students.append({
        "id": student_id,
        "model": model,
        "persona": persona,
        "options": options,
        "status": "active",
        "added": f"{datetime.now(timezone.utc):%Y-%m-%d}",
    })
    save_students(students, path)
    return students


def retire_student(student_id: str, reason: str = "", path: Optional[Path] = None) -> list[dict]:
    """Mark a student retired (kept in the file for history)."""
    students = load_students(path)
    for s in students:
        if s.get("id") == student_id:
            s["status"] = "retired"
            s["retired"] = f"{datetime.now(timezone.utc):%Y-%m-%d}"
            if reason:
                s["retired_reason"] = reason
            save_students(students, path)
            return students
    raise ValueError(f"no such student: {student_id}")


# ── track record ──────────────────────────────────────────────────────────


def student_scores(scores_path: Optional[Path] = None) -> dict[str, list[float]]:
    """student_id → chronological totals from scores.jsonl (legacy lines without
    student_id are attributed to 'legacy')."""
    p = Path(scores_path) if scores_path else RADAR_DIR / "training" / "scores.jsonl"
    out: dict[str, list[float]] = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        total = rec.get("total")
        if total is None:
            continue
        out.setdefault(rec.get("student_id") or "legacy", []).append(float(total))
    return out


def leaderboard(
    students: list[dict],
    scores: dict[str, list[float]],
    window: int = 10,
) -> list[dict]:
    """Per-student rolling mean over the last ``window`` runs, best first."""
    rows: list[dict] = []
    for s in students:
        sid = s.get("id", "?")
        history = scores.get(sid, [])
        recent = history[-window:]
        rows.append({
            "id": sid,
            "model": s.get("model", ""),
            "status": s.get("status", "active"),
            "runs": len(history),
            "rolling_mean": round(sum(recent) / len(recent), 1) if recent else None,
            "last": recent[-1] if recent else None,
        })
    rows.sort(key=lambda r: (r["rolling_mean"] is not None, r["rolling_mean"] or 0), reverse=True)
    return rows


def retirement_suggestions(
    board: list[dict],
    margin: float = 10.0,
    min_runs: int = 5,
) -> list[str]:
    """Students whose rolling mean trails the leader by > margin (with enough
    runs to trust the gap). Suggestion only — retirement stays human-confirmed."""
    scored = [r for r in board if r["rolling_mean"] is not None and r["status"] == "active"]
    if len(scored) < 2:
        return []
    top = scored[0]["rolling_mean"]
    return [
        r["id"]
        for r in scored[1:]
        if r["runs"] >= min_runs and (top - r["rolling_mean"]) > margin
    ]

# -*- coding: utf-8 -*-
"""Tests for the student roster + mentor panel (pure, offline logic only)."""

import json

import pytest

import agent_reach.radar_report as rr
import agent_reach.radar_students as rs
from agent_reach.radar_report import (
    ASSISTANT_SYSTEM,
    DEFAULT_ASSISTANTS,
    _drafts_block,
    _extract_json,
    assistant_critique,
    mentor_critique,
)
from agent_reach.radar_students import (
    add_student,
    active_students,
    leaderboard,
    load_students,
    retire_student,
    retirement_suggestions,
    student_scores,
)


# ── roster ────────────────────────────────────────────────────────────────


def test_load_students_seeds_default_roster(tmp_path):
    p = tmp_path / "students.yaml"
    students = load_students(p)
    assert p.exists()
    assert len(students) == 2
    assert all(s["model"] == "qwen3:4b" for s in students)
    assert all(s["status"] == "active" for s in students)
    # Personas differ so drafts diverge.
    assert students[0]["persona"] != students[1]["persona"]


def test_add_and_retire_student(tmp_path):
    p = tmp_path / "students.yaml"
    load_students(p)
    add_student("nemotron-x", "nemotron:latest", persona="新秀", seed=1, path=p)
    students = load_students(p)
    assert any(s["id"] == "nemotron-x" for s in students)

    retire_student("nemotron-x", reason="被新 qwen 取代", path=p)
    students = load_students(p)
    retired = next(s for s in students if s["id"] == "nemotron-x")
    assert retired["status"] == "retired"
    assert retired["retired_reason"] == "被新 qwen 取代"
    assert all(s["id"] != "nemotron-x" for s in active_students(students))


def test_add_duplicate_id_rejected(tmp_path):
    p = tmp_path / "students.yaml"
    load_students(p)
    add_student("a", "m", path=p)
    with pytest.raises(ValueError):
        add_student("a", "m2", path=p)


def test_retire_unknown_raises(tmp_path):
    p = tmp_path / "students.yaml"
    load_students(p)
    with pytest.raises(ValueError):
        retire_student("ghost", path=p)


# ── track record ──────────────────────────────────────────────────────────


def _write_scores(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_student_scores_groups_by_id_and_handles_legacy(tmp_path):
    p = tmp_path / "scores.jsonl"
    _write_scores(p, [
        {"date": "d1", "student_id": "a", "total": 70},
        {"date": "d2", "student_id": "a", "total": 80},
        {"date": "d3", "total": 60},  # legacy line without student_id
        {"date": "d4", "student_id": "b"},  # no total → skipped
    ])
    scores = student_scores(p)
    assert scores["a"] == [70.0, 80.0]
    assert scores["legacy"] == [60.0]
    assert "b" not in scores


def test_leaderboard_rolling_mean_and_order():
    students = [
        {"id": "a", "model": "m1", "status": "active"},
        {"id": "b", "model": "m2", "status": "active"},
        {"id": "c", "model": "m3", "status": "active"},  # no runs yet
    ]
    scores = {"a": [50.0] * 20 + [90.0] * 10, "b": [70.0] * 6}
    board = leaderboard(students, scores, window=10)
    assert [r["id"] for r in board] == ["a", "b", "c"]
    assert board[0]["rolling_mean"] == 90.0  # window ignores the old 50s
    assert board[0]["runs"] == 30
    assert board[2]["rolling_mean"] is None


def test_retirement_suggestions_need_margin_and_runs():
    board = [
        {"id": "top", "rolling_mean": 90.0, "runs": 10, "status": "active"},
        {"id": "laggard", "rolling_mean": 70.0, "runs": 10, "status": "active"},
        {"id": "rookie", "rolling_mean": 60.0, "runs": 2, "status": "active"},  # too few runs
        {"id": "close", "rolling_mean": 85.0, "runs": 10, "status": "active"},  # within margin
    ]
    assert retirement_suggestions(board, margin=10.0, min_runs=5) == ["laggard"]


def test_retirement_suggestions_empty_with_one_scored():
    board = [{"id": "only", "rolling_mean": 50.0, "runs": 9, "status": "active"}]
    assert retirement_suggestions(board) == []


# ── mentor panel ──────────────────────────────────────────────────────────


def test_extract_json_from_fenced_output():
    out = _extract_json('前言\n```json\n{"total": 88}\n```\n後記')
    assert out == {"total": 88}


def test_extract_json_raw_fallback():
    assert _extract_json("no json here") == {"raw": "no json here"}


def test_drafts_block_labels_each_student():
    block = _drafts_block({"a": "草稿A", "b": "草稿B"})
    assert "學生 a" in block and "草稿A" in block
    assert "學生 b" in block and "草稿B" in block


def test_assistant_critique_skipped_without_key(monkeypatch):
    monkeypatch.setattr(rr, "_panel_chat", lambda *a, **k: None)
    out = assistant_critique({"a": "d"}, "material", DEFAULT_ASSISTANTS[0])
    assert out is None


def test_assistant_critique_tags_assistant_name(monkeypatch):
    monkeypatch.setattr(
        rr, "_panel_chat",
        lambda *a, **k: '{"per_student": {"a": {"total": 75}}, "issues": ["x"]}',
    )
    out = assistant_critique({"a": "d"}, "material", {"provider": "xai", "model": "grok-4", "name": "Grok"})
    assert out["assistant"] == "Grok"
    assert out["per_student"]["a"]["total"] == 75


def test_mentor_critique_none_without_key(monkeypatch):
    monkeypatch.setattr(rr, "_panel_chat", lambda *a, **k: None)
    assert mentor_critique({"a": "d"}, "material") is None


def test_mentor_critique_includes_assistant_notes(monkeypatch):
    captured = {}

    def fake_panel(provider, model, system, user, config=None, temperature=None):
        captured["provider"] = provider
        captured["model"] = model
        captured["user"] = user
        return '{"per_student": {"a": {"scores": {}, "total": 91}}, "best_student": "a", "issues": [], "gold_report": "# g"}'

    monkeypatch.setattr(rr, "_panel_chat", fake_panel)
    out = mentor_critique(
        {"a": "draft"}, "material",
        assistant_notes=[{"assistant": "Grok", "per_student": {"a": {"total": 60}}}],
    )
    assert captured["provider"] == "anthropic"
    assert captured["model"] == rr.DEFAULT_MENTOR_MODEL  # Fable 5 is the main teacher
    assert "助教 Grok" in captured["user"]
    assert out["best_student"] == "a"


def test_panel_chat_unknown_provider_returns_none():
    assert rr._panel_chat("nope", "m", "s", "u") is None


def test_assistant_system_demands_per_student_json():
    assert "per_student" in ASSISTANT_SYSTEM
    assert "gold" not in ASSISTANT_SYSTEM  # assistants critique, never rewrite

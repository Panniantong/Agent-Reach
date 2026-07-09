# -*- coding: utf-8 -*-
"""Tests for the self-evolve harness (pure, offline logic only)."""

import json

import pytest

import agent_reach.radar_evolve as ev
from agent_reach.radar_evolve import (
    ALLOWED_FILES,
    Mutation,
    _mutation_allowed,
    _parse_tagged_json,
    append_journal,
    cached_baseline,
    compute_manifest_hashes,
    decide,
    journal_tail_text,
    propose_mutation,
    read_journal,
    rebuild_journal_md,
    verify_manifest,
)


# ── allowlist / decision ──────────────────────────────────────────────────


def test_mutation_allowed_subset_of_allowlist():
    assert _mutation_allowed(["agent_reach/radar_report.py"])
    assert _mutation_allowed(["evolve/radar.yaml"])
    # Windows-style paths normalize.
    assert _mutation_allowed(["agent_reach\\radar.py"])


def test_mutation_rejected_outside_allowlist():
    assert not _mutation_allowed(["agent_reach/radar_evolve.py"])  # the harness itself
    assert not _mutation_allowed(["tests/test_radar.py"])
    assert not _mutation_allowed(["evolve/fixtures/manifest.json"])
    assert not _mutation_allowed(["evolve/program.md"])
    # One legal + one illegal file → still rejected.
    assert not _mutation_allowed(["agent_reach/radar.py", "tests/conftest.py"])
    # No change at all is not a valid experiment.
    assert not _mutation_allowed([])


def test_decide_epsilon():
    assert decide(80.0, 81.0, epsilon=1.0) == "keep"
    assert decide(80.0, 80.9, epsilon=1.0) == "discard"
    assert decide(80.0, 95.0, epsilon=1.0) == "keep"
    assert decide(80.0, 80.0, epsilon=0.0) == "keep"


# ── manifest ──────────────────────────────────────────────────────────────


def _make_repo(tmp_path):
    (tmp_path / "agent_reach").mkdir()
    (tmp_path / "agent_reach" / "radar_evolve.py").write_text("harness", encoding="utf-8")
    fx = tmp_path / "evolve" / "fixtures"
    (fx / "heldout").mkdir(parents=True)
    (fx / "heldout" / "fixture-01.json").write_text('{"material": "m"}', encoding="utf-8")
    (tmp_path / "evolve" / "program.md").write_text("goals", encoding="utf-8")
    return tmp_path


def _write_manifest(repo):
    mf = repo / "evolve" / "fixtures" / "manifest.json"
    manifest = {
        "pinned_student": {"id": "eval-pinned", "model": "qwen3:4b", "options": {"temperature": 0}},
        "pinned_mentor": "claude-fable-5",
        "hashes": compute_manifest_hashes(repo),
    }
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    return mf


def test_manifest_roundtrip_ok(tmp_path):
    repo = _make_repo(tmp_path)
    _write_manifest(repo)
    ok, msg = verify_manifest(repo)
    assert ok, msg


def test_manifest_detects_harness_tampering(tmp_path):
    repo = _make_repo(tmp_path)
    _write_manifest(repo)
    (repo / "agent_reach" / "radar_evolve.py").write_text("hacked harness", encoding="utf-8")
    ok, msg = verify_manifest(repo)
    assert not ok
    assert "radar_evolve.py" in msg


def test_manifest_detects_fixture_tampering(tmp_path):
    repo = _make_repo(tmp_path)
    _write_manifest(repo)
    (repo / "evolve" / "fixtures" / "heldout" / "fixture-01.json").write_text(
        '{"material": "easier material"}', encoding="utf-8"
    )
    ok, _ = verify_manifest(repo)
    assert not ok


def test_manifest_missing_refuses(tmp_path):
    repo = _make_repo(tmp_path)
    ok, msg = verify_manifest(repo)
    assert not ok
    assert "freeze" in msg


# ── journal ───────────────────────────────────────────────────────────────


def test_journal_roundtrip_and_md(tmp_path):
    j = tmp_path / "journal.jsonl"
    append_journal({"baseline_sha": "abc123", "score": 77.5}, journal=j)
    append_journal({
        "id": "20260709-01", "decision": "keep", "file": "agent_reach/radar_report.py",
        "hypothesis": "透鏡規則前置", "base_score": 77.5, "cand_score": 80.1,
        "pytest_ok": True, "health_ok": True,
    }, journal=j)
    rows = read_journal(j)
    assert len(rows) == 2
    assert cached_baseline("abc123", journal=j) == 77.5
    assert cached_baseline("nope", journal=j) is None

    tail = journal_tail_text(journal=j)
    assert "20260709-01" in tail and "keep" in tail
    assert "abc123" not in tail  # baseline rows are not experiments

    md = tmp_path / "journal.md"
    rebuild_journal_md(journal=j, out=md)
    body = md.read_text(encoding="utf-8")
    assert "| 20260709-01 | keep |" in body
    assert "透鏡規則前置" in body


def test_journal_skips_corrupt_lines(tmp_path):
    j = tmp_path / "journal.jsonl"
    j.write_text('{"id": "a", "decision": "keep"}\nnot json\n', encoding="utf-8")
    assert len(read_journal(j)) == 1


# ── proposer validation ───────────────────────────────────────────────────


def test_propose_mutation_valid(monkeypatch):
    payload = {
        "file": "agent_reach/radar_report.py",
        "kind": "prompt",
        "hypothesis": "把透鏡規則提到最前",
        "new_content": "# new file content",
    }
    monkeypatch.setattr(
        "agent_reach.radar_report._panel_chat", lambda *a, **k: json.dumps(payload)
    )
    m = propose_mutation("program", "", {}, None)
    assert isinstance(m, Mutation)
    assert m.file in ALLOWED_FILES
    assert m.kind == "prompt"


def test_propose_mutation_rejects_illegal_file(monkeypatch):
    payload = {"file": "tests/test_radar.py", "kind": "code", "hypothesis": "h", "new_content": "x"}
    monkeypatch.setattr(
        "agent_reach.radar_report._panel_chat", lambda *a, **k: json.dumps(payload)
    )
    assert propose_mutation("program", "", {}, None) is None


def test_propose_mutation_rejects_empty_content(monkeypatch):
    payload = {"file": "evolve/radar.yaml", "kind": "config", "hypothesis": "h", "new_content": "  "}
    monkeypatch.setattr(
        "agent_reach.radar_report._panel_chat", lambda *a, **k: json.dumps(payload)
    )
    assert propose_mutation("program", "", {}, None) is None


def test_propose_mutation_none_without_key(monkeypatch):
    monkeypatch.setattr("agent_reach.radar_report._panel_chat", lambda *a, **k: None)
    assert propose_mutation("program", "", {}, None) is None


# ── misc helpers ──────────────────────────────────────────────────────────


def test_parse_tagged_json_takes_last_match():
    out = "noise\nEVOLVE_RESULT {\"draft\": \"a\"}\nmore\nEVOLVE_RESULT {\"draft\": \"b\"}\n"
    assert _parse_tagged_json(out, "EVOLVE_RESULT") == {"draft": "b"}
    assert _parse_tagged_json("nothing", "EVOLVE_RESULT") is None
    assert _parse_tagged_json("EVOLVE_RESULT not-json", "EVOLVE_RESULT") is None


def test_eval_mentor_system_is_frozen_in_harness():
    # The grading rubric must live in the harness (hash-protected), not in
    # agent-editable radar_report.py — otherwise mutations could game it.
    assert "coverage" in ev.EVAL_MENTOR_SYSTEM
    assert "EVAL_MENTOR_SYSTEM" not in ALLOWED_FILES  # sanity: harness not editable


def test_run_evolve_stops_on_stop_file(tmp_path, monkeypatch):
    stop = tmp_path / "STOP"
    stop.write_text("", encoding="utf-8")
    monkeypatch.setattr(ev, "STOP_FILE", stop)
    monkeypatch.setattr(ev, "preflight", lambda config=None, repo_root=None: (True, "ok"))
    monkeypatch.setattr(ev, "_git", lambda args, cwd, timeout=180: type(
        "CP", (), {"returncode": 0, "stdout": "abc\n", "stderr": ""}
    )())
    results = ev.run_evolve(budget=3, repo_root=tmp_path)
    assert results == []  # halted before the first experiment


def test_preflight_blocks_on_stop(tmp_path, monkeypatch):
    stop = tmp_path / "STOP"
    stop.write_text("", encoding="utf-8")
    monkeypatch.setattr(ev, "STOP_FILE", stop)
    ok, msg = ev.preflight(repo_root=tmp_path)
    assert not ok
    assert "STOP" in msg

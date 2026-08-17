# -*- coding: utf-8
"""Tests for P2: experience consolidation + weekly harness dedupe."""

import json
import tempfile
from pathlib import Path

import agent_reach.daily_run.harness as harness_mod
from agent_reach.daily_run.experience import append_experience_entry, load_experience_rules
from agent_reach.daily_run.harness import refine_after_job


def test_experience_consolidated_skips_rules_in_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_reach.daily_run.experience.experience_dir", lambda: tmp_path)
    monkeypatch.setattr(harness_mod, "_state_path", lambda: tmp_path / "harness_state.json")
    settings = {
        "harness": {
            "enabled": True,
            "threshold_evolution_mode": "harness",
            "jobs": {"experience": True},
        },
        "experience": {"enabled": True, "harness_evolve": True, "harness_consolidate": True},
    }
    append_experience_entry(
        {"name": "澜起", "mss_final": 31},
        {"verdict_current": "回避", "mss_within_prediction": False},
        settings=settings,
    )
    entry = json.loads((tmp_path / "experience.jsonl").read_text(encoding="utf-8").strip())
    assert entry.get("rules") == []
    assert entry.get("rules_in_harness") is True
    assert not (tmp_path / "rules_summary.json").exists()


def test_load_experience_rules_from_harness(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_mod, "_state_path", lambda: tmp_path / "harness_state.json")
    settings = {
        "harness": {
            "enabled": True,
            "threshold_evolution_mode": "harness",
            "jobs": {"experience": True},
        },
        "experience": {"harness_evolve": True, "harness_consolidate": True},
    }
    refine_after_job(
        "experience",
        evidence={
            "memory": ["宏观一票否决生效：维持高现金，禁止接飞刀"],
            "summary": "test",
        },
        settings=settings,
    )
    rules = load_experience_rules(5, settings=settings)
    assert any("宏观一票否决" in r for r in rules)


def test_experience_close_to_load_rules_e2e(tmp_path, monkeypatch):
    """Close append_experience_entry → harness memory → load_experience_rules."""
    monkeypatch.setattr("agent_reach.daily_run.experience.experience_dir", lambda: tmp_path)
    monkeypatch.setattr(harness_mod, "_state_path", lambda: tmp_path / "harness_state.json")
    settings = {
        "harness": {
            "enabled": True,
            "threshold_evolution_mode": "harness",
            "jobs": {"experience": True},
            "llm_refine": {"enabled": False, "summarize_enabled": False},
        },
        "experience": {"enabled": True, "harness_evolve": True, "harness_consolidate": True},
    }
    append_experience_entry(
        {"name": "澜起科技", "mss_final": 31, "portfolio": {"cash_ratio": 0.55}},
        {"verdict_current": "回避", "mss_within_prediction": False},
        settings=settings,
    )
    line = (tmp_path / "experience.jsonl").read_text(encoding="utf-8").strip()
    entry = json.loads(line)
    assert entry.get("rules") == []
    assert entry.get("rules_in_harness") is True
    assert entry.get("harness_refinement_id")

    rules = load_experience_rules(5, settings=settings)
    assert any("宏观一票否决" in r or "接飞刀" in r for r in rules)


def test_weekly_layer_a_skips_process_improvements_when_specialized(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_mod, "_state_path", lambda: tmp_path / "harness_state.json")
    settings = {
        "harness": {
            "enabled": True,
            "jobs": {"weekly": True, "skill_closure": True, "run_guard": True},
        }
    }
    ref = refine_after_job(
        "weekly",
        evidence={
            "report": {
                "week_start": "2026-08-10",
                "week_end": "2026-08-14",
                "weekly_pnl": -1200,
                "weekly_pnl_pct": -1.2,
                "process_improvements": [
                    {
                        "category": "schedule",
                        "priority": "high",
                        "title": "缺失早盘",
                        "detail": "2 天",
                        "action": "补跑 morning",
                    }
                ],
                "skill_learning": [{"title": "技能", "summary": "不应写入"}],
                "experience_snippets": ["2026-08-14 澜起 MSS=31"],
            },
            "applied_config": ["thresholds.macro_veto: 40 → 38"],
        },
        settings=settings,
    )
    assert ref.get("skipped") is False
    state = json.loads((tmp_path / "harness_state.json").read_text(encoding="utf-8"))
    blob = json.dumps(state, ensure_ascii=False)
    assert "缺失早盘" not in blob
    assert "不应写入" not in blob
    assert "本周组合净值" in blob
    assert "2026-08-14 澜起" in blob
    assert "macro_veto" in blob

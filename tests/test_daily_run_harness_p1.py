# -*- coding: utf-8
"""Tests for P1 harness skills: experience, morning, intraday, run_guard."""

import json
from datetime import date

import agent_reach.daily_run.harness as harness_mod
from agent_reach.daily_run.experience_harness import (
    apply_experience_harness_refinement,
    experience_to_harness_evidence,
)
from agent_reach.daily_run.intraday_harness import intraday_to_harness_evidence
from agent_reach.daily_run.morning_harness import morning_to_harness_evidence
from agent_reach.daily_run.run_guard_harness import (
    apply_run_guard_harness_refinement,
    guard_event_to_harness_evidence,
    schedule_gaps_to_harness_evidence,
)


def test_experience_rules_map_to_memory():
    ev = experience_to_harness_evidence(
        {"name": "澜起科技", "mss_final": 31},
        {
            "verdict_current": "回避",
            "mss_within_prediction": False,
            "deviations": ["价格变动 9%"],
        },
        rules=["MSS 预测偏离：下日调低进攻阈值或缩窄仓位"],
    )
    blob = " ".join(ev["memory"])
    assert "MSS 预测偏离" in blob
    assert ev["playbook"]


def test_morning_avoid_verdict():
    ev = morning_to_harness_evidence(
        {
            "snapshot": {"name": "澜起科技", "portfolio": {"cash_ratio": 0.5}},
            "evaluation": {
                "report": {"name": "澜起科技", "mss_final": 28, "verdict": "回避"},
                "gate": type("G", (), {"passed": True, "summary": lambda: ""})(),
                "audit": type("A", (), {"passed": True, "summary": lambda: ""})(),
            },
        }
    )
    assert any("宏观一票否决" in m for m in ev["memory"])


def test_intraday_sparse_scans():
    ev = intraday_to_harness_evidence(
        {
            "scan": {
                "scan": {"scan_id": "S3", "name": "澜起", "mss_final": 45},
                "trend": "flat",
                "lookback_mss": 42,
                "state": {"scans": [{"scan_id": "S1"}, {"scan_id": "S2"}]},
            },
            "scan_count": 2,
        }
    )
    assert any("扫描偏少" in m for m in ev["memory"])


def test_run_guard_dedupe_event():
    ev = guard_event_to_harness_evidence("close", reason="manifest 去重", guard="dedupe")
    assert ev["memory"]
    assert ev["playbook"]


def test_schedule_gaps_missing_morning():
    ev = schedule_gaps_to_harness_evidence(
        week_start=date(2026, 8, 10),
        manifests=[{"_run_date": "2026-08-11", "job": "close"}],
    )
    assert any("早盘" in m for m in ev["memory"])
    assert ev["plan"]


def test_apply_experience_writes_harness(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_mod, "_state_path", lambda: tmp_path / "harness_state.json")
    settings = {
        "harness": {
            "enabled": True,
            "threshold_evolution_mode": "harness",
            "jobs": {"experience": True},
        },
        "experience": {"harness_evolve": True},
    }
    ref = apply_experience_harness_refinement(
        {"name": "澜起"},
        {"verdict_current": "回避", "mss_within_prediction": False},
        rules=["宏观一票否决生效：维持高现金，禁止接飞刀"],
        settings=settings,
    )
    assert ref.get("skipped") is False
    state = json.loads((tmp_path / "harness_state.json").read_text(encoding="utf-8"))
    assert "宏观一票否决" in json.dumps(state, ensure_ascii=False)


def test_apply_run_guard_writes_harness(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_mod, "_state_path", lambda: tmp_path / "harness_state.json")
    settings = {
        "harness": {"enabled": True, "jobs": {"run_guard": True}},
        "schedule": {"guard": {"harness_evolve": True}},
    }
    ref = apply_run_guard_harness_refinement(
        "morning",
        reason="今日早盘已成功执行",
        guard="dedupe",
        settings=settings,
    )
    assert ref.get("skipped") is False

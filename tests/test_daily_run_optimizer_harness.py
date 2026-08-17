# -*- coding: utf-8
"""Tests for optimizer harness + close job dedupe."""

import json
from pathlib import Path

import agent_reach.daily_run.harness as harness_mod
from agent_reach.daily_run.harness import refine_after_job
from agent_reach.daily_run.optimizer import grid_search_optimize, save_optimized_settings
from agent_reach.daily_run.optimizer_harness import optimize_to_harness_evidence
from agent_reach.daily_run.settings import load_settings


def test_optimize_to_harness_evidence_has_policy():
    history = json.loads(
        Path("config/daily_run_history.example.json").read_text(encoding="utf-8")
    )
    result = grid_search_optimize(history, load_settings(), objective="excess_return")
    ev = optimize_to_harness_evidence(result)
    assert ev["policy"]
    assert any("macro_veto=" in p for p in ev["policy"])
    assert ev["playbook"]


def test_save_optimized_settings_harness_mode_skips_thresholds(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_mod, "_state_path", lambda: tmp_path / "harness_state.json")
    history = json.loads(
        Path("config/daily_run_history.example.json").read_text(encoding="utf-8")
    )
    settings = load_settings()
    settings.setdefault("harness", {})
    settings["harness"]["enabled"] = True
    settings["harness"]["threshold_evolution_mode"] = "harness"
    settings["harness"]["jobs"] = {"optimize": True}
    settings.setdefault("optimizer", {})["harness_evolve"] = True
    settings.setdefault("thresholds", {})
    settings["thresholds"]["macro_veto"] = 99

    result = grid_search_optimize(history, settings)
    out = save_optimized_settings(result, settings, path=tmp_path / "opt.json")
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["thresholds"].get("macro_veto") == 99
    assert saved["optimizer"]["last_run"]["harness_mode"] is True
    state = json.loads((tmp_path / "harness_state.json").read_text(encoding="utf-8"))
    policy_blob = json.dumps(state.get("entries", {}).get("policy", {}), ensure_ascii=False)
    assert "macro_veto=" in policy_blob


def test_close_layer_a_skips_verify_when_specialized_jobs_on(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_mod, "_state_path", lambda: tmp_path / "harness_state.json")
    settings = {
        "harness": {
            "enabled": True,
            "jobs": {"close": True, "verify": True, "close_improve": True},
        }
    }
    close_evidence = {
        "verify": {
            "summary": "验证完成",
            "recommendations": ["明日激进建仓"],
            "code": "688008",
        },
        "name": "澜起科技",
        "portfolio_summary": {"daily_pnl": 1200.0, "daily_pnl_pct": 0.5},
    }
    ref = refine_after_job("close", evidence=close_evidence, settings=settings)
    assert ref.get("skipped") is False
    state = json.loads((tmp_path / "harness_state.json").read_text(encoding="utf-8"))
    blob = json.dumps(state, ensure_ascii=False)
    assert "激进建仓" not in blob
    assert "收盘组合盈亏" in blob

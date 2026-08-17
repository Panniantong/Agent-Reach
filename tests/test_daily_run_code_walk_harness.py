# -*- coding: utf-8
"""Tests for code walk harness self-evolution."""

from agent_reach.daily_run.close_code_review import CodeFinding, CodeReviewResult
from agent_reach.daily_run.close_code_review import list_walk_module_names
from agent_reach.daily_run.code_walk_harness import (
    apply_code_walk_harness_refinement,
    finding_to_harness_lines,
    findings_to_harness_evidence,
    run_agent_code_walk,
)
from agent_reach.daily_run.harness import load_harness
from agent_reach.daily_run.settings import load_settings


def test_finding_to_harness_overlay_policy():
    finding = CodeFinding(
        "harness",
        "high",
        "settings 未应用 harness overlay",
        "调用方须先 effective_settings()",
    )
    memory, policy, playbook, plan = finding_to_harness_lines(finding)
    assert any("effective_settings" in p for p in policy)
    assert plan


def test_apply_code_walk_writes_harness_memory(tmp_path, monkeypatch):
    state_path = tmp_path / "harness_state.json"
    monkeypatch.setattr("agent_reach.daily_run.harness._state_path", lambda: state_path)

    settings = load_settings()
    settings.setdefault("harness", {})["enabled"] = True
    settings["harness"]["threshold_evolution_mode"] = "harness"
    settings.setdefault("harness", {}).setdefault("jobs", {})["code_walk"] = True
    settings.setdefault("close_code_review", {})["harness_evolve_on_walk"] = True

    result = CodeReviewResult(
        findings=[
            CodeFinding(
                "harness",
                "high",
                "settings 未应用 harness overlay",
                "须 effective_settings()",
            )
        ]
    )
    ref = apply_code_walk_harness_refinement(result, settings=settings)
    assert ref.get("skipped") is False
    assert ref.get("refinement_id")

    state = load_harness()
    memory_blob = " ".join(e.content for e in state.entries.get("memory", {}).values())
    policy_blob = " ".join(e.content for e in state.entries.get("policy", {}).values())
    assert "effective_settings" in policy_blob or "代码走读" in memory_blob


def test_findings_to_harness_evidence_dedupes():
    finding = CodeFinding("portfolio", "high", "days_held 与 acquired_date 不一致", "0 vs 1")
    ev = findings_to_harness_evidence([finding, finding], fixes=["days_held 0 → 1"])
    assert len(ev["memory"]) >= 1
    assert len(ev["playbook"]) >= 1


def test_run_agent_code_walk_smoke(monkeypatch):
    settings = load_settings()
    settings.setdefault("harness", {})["enabled"] = True
    settings.setdefault("close_code_review", {})["harness_evolve_on_walk"] = True
    monkeypatch.setattr(
        "agent_reach.daily_run.code_walk_harness.load_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "agent_reach.daily_run.settings.load_settings",
        lambda path=None: settings,
    )

    def _fake_portfolio():
        raise FileNotFoundError

    monkeypatch.setattr(
        "agent_reach.daily_run.snapshot_builder.load_portfolio",
        _fake_portfolio,
    )
    report = run_agent_code_walk(
        portfolio={"holdings": [], "watchlist": [], "cash": 1, "total": 1, "cash_ratio": 1},
        settings=settings,
        walk_source=False,
        evolve_harness=False,
    )
    assert report.review is not None


def test_list_walk_module_names_includes_harness_modules():
    names = list_walk_module_names()
    assert "workflows.py" in names
    assert "experience_harness.py" in names
    assert "close_harness_skills.py" in names
    assert "verify_harness.py" in names
    assert len(names) > len(
        (
            "portfolio_manager.py",
            "watchlist_manager.py",
            "intraday.py",
            "schedule.py",
            "workflows.py",
            "close_improvements.py",
            "close_code_review.py",
            "snapshot_builder.py",
            "harness_policy.py",
            "settings.py",
            "verify.py",
        )
    )

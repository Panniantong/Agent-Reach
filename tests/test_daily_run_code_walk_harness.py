# -*- coding: utf-8
"""Tests for code walk harness self-evolution."""

from agent_reach.daily_run.close_code_review import CodeFinding, CodeReviewResult
from agent_reach.daily_run.close_code_review import list_walk_module_names
from agent_reach.daily_run.code_walk_harness import (
    apply_code_walk_harness_refinement,
    external_review_to_findings,
    finding_to_harness_lines,
    findings_to_harness_evidence,
    harness_evidence_findings,
    run_agent_code_walk,
    scan_diff_review,
    scan_macro_source_audit,
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


def test_finding_to_harness_macro_source_policy():
    finding = CodeFinding(
        "source",
        "high",
        "盘中数据来源审计未通过（macro_ctx.sources）",
        "缺少数据来源类别：flow, sentiment",
    )
    memory, policy, playbook, plan = finding_to_harness_lines(finding)
    assert any("intraday_block" in p for p in policy)
    assert any("macro_ctx" in p for p in policy)
    assert plan


def test_harness_evidence_skips_medium_diff():
    findings = [
        CodeFinding("diff", "medium", "裸读 evolved", "detail"),
        CodeFinding("diff", "high", "load_settings 未 overlay", "detail"),
        CodeFinding("source", "medium", "raw incomplete", "detail"),
    ]
    eligible = harness_evidence_findings(findings)
    assert len(eligible) == 2
    assert all(f.area != "diff" or f.severity == "high" for f in eligible)


def test_external_review_to_findings_maps_critical_to_high():
    items = [
        {
            "severity": "critical",
            "location": "agent_reach/daily_run/foo.py:10",
            "description": "unsafe eval",
            "suggested_fix": "remove eval",
        }
    ]
    out = external_review_to_findings(items)
    assert len(out) == 1
    assert out[0].severity == "high"
    assert out[0].area == "diff"
    assert "foo.py" in out[0].detail


def test_scan_macro_source_audit_incomplete(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_path = cache_dir / "2026-08-20.json"
    cache_path.write_text(
        '{"macro_ctx": {"sources": {"quote": {"summary": "上证 +1%"}}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "agent_reach.daily_run.snapshot_cache.cache_dir",
        lambda: cache_dir,
    )
    monkeypatch.setattr(
        "agent_reach.daily_run.snapshot_cache.today_shanghai",
        lambda: __import__("datetime").date(2026, 8, 20),
    )
    portfolio = {"holdings": [], "watchlist": [], "sources_overrides": {}}
    findings = scan_macro_source_audit(portfolio=portfolio)
    titles = " ".join(f.title for f in findings)
    assert "raw sources" in titles or "审计未通过" in titles
    high = [f for f in findings if f.severity == "high"]
    assert high
    assert "flow" in high[0].detail


def test_scan_diff_review_no_changes(monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.code_walk_harness._git_diff_paths",
        lambda **kwargs: ([], ""),
    )
    findings, meta = scan_diff_review()
    assert findings == []
    assert meta.get("skipped") is True


def test_scan_diff_review_detects_load_settings(monkeypatch):
    path = "agent_reach/daily_run/foo.py"
    diff = (
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1,2 @@\n"
        "+    cfg = load_settings()\n"
    )
    monkeypatch.setattr(
        "agent_reach.daily_run.code_walk_harness._git_diff_paths",
        lambda **kwargs: ([path], ""),
    )
    monkeypatch.setattr(
        "agent_reach.daily_run.code_walk_harness._git_diff_text",
        lambda **kwargs: diff,
    )
    findings, meta = scan_diff_review()
    assert meta.get("agent_instructions")
    high = [f for f in findings if f.severity == "high"]
    assert any("load_settings" in f.title for f in high)


def test_run_agent_code_walk_includes_macro_audit(monkeypatch):
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
    monkeypatch.setattr(
        "agent_reach.daily_run.code_walk_harness.scan_macro_source_audit",
        lambda portfolio=None, settings=None: [
            CodeFinding("source", "medium", "macro 缓存 raw sources 不完整", "缺少 raw 类别：flow")
        ],
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
    assert report.macro_findings
    assert any(f.area == "source" for f in report.all_findings())

# -*- coding: utf-8
"""Tests for verify/close_improve/data_audit/skill_closure harness skills."""

from agent_reach.daily_run.auditor import AuditResult
from agent_reach.daily_run.close_improvements import CloseImprovements
from agent_reach.daily_run.close_improve_harness import improvements_to_harness_evidence
from agent_reach.daily_run.data_audit_harness import audit_to_harness_evidence
from agent_reach.daily_run.skill_closure_harness import (
    apply_skill_closure_harness_refinement,
    weekly_report_to_harness_evidence,
)
from agent_reach.daily_run.verify_harness import verify_to_harness_evidence


def test_verify_deviation_maps_to_harness_memory():
    ev = verify_to_harness_evidence(
        {
            "name": "澜起科技",
            "summary": "验证完成",
            "deviations": ["价格变动 9.2% 超过锚点阈值 8.0%"],
            "mss_within_prediction": False,
            "recommendations": ["维持高现金，取消一切买入计划"],
        }
    )
    blob = " ".join(ev["memory"])
    assert "MSS 预测偏离" in blob
    assert "偏差" in blob
    assert any("维持高现金" in m for m in ev["memory"])


def test_close_improve_schedule_scan_sparse():
    out = CloseImprovements()
    out.add("schedule", "medium", "盘中扫描偏少", "intraday 仅 2 次")
    ev = improvements_to_harness_evidence(out)
    assert any("扫描偏少" in m for m in ev["memory"])


def test_audit_issue_maps_to_plan():
    ev = audit_to_harness_evidence(
        AuditResult(passed=False, issues=["缺少数据来源类别：quote"], warnings=["行情覆盖率 70% 低于阈值"])
    )
    assert ev["plan"]
    assert any("quote" in p for p in ev["plan"])


def test_weekly_skill_closure_evidence():
    ev = weekly_report_to_harness_evidence(
        {
            "week_start": "2026-08-10",
            "week_end": "2026-08-14",
            "process_improvements": [
                {
                    "category": "mss",
                    "priority": "high",
                    "title": "MSS 预测未命中",
                    "detail": "3 次偏离",
                    "action": "增大 base_spread",
                }
            ],
        }
    )
    assert any("MSS 预测偏离" in m for m in ev["memory"])
    assert ev["playbook"]


def test_apply_skill_closure_writes_harness(tmp_path, monkeypatch):
    import agent_reach.daily_run.harness as h

    monkeypatch.setattr(h, "_state_path", lambda: tmp_path / "harness_state.json")
    settings = {
        "harness": {
            "enabled": True,
            "threshold_evolution_mode": "harness",
            "jobs": {"skill_closure": True},
        },
        "weekly_report": {"harness_evolve": True},
    }
    ref = apply_skill_closure_harness_refinement(
        {
            "week_start": "2026-08-10",
            "week_end": "2026-08-14",
            "process_improvements": [
                {"category": "mss", "priority": "high", "title": "预测未命中", "detail": "x"}
            ],
        },
        settings=settings,
    )
    assert ref.get("skipped") is False
    assert ref.get("refinement_id")

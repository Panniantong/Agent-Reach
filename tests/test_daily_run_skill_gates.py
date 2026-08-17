# -*- coding: utf-8
"""Tests for Saturday skill mechanical gates."""

from typing import Any

import pytest

from agent_reach.daily_run.skill_gates import (
    format_gate_alert_markdown,
    gates_enabled,
    run_skill_gates,
)
from agent_reach.daily_run.skill_improvements_apply import (
    REQUIRED_SKILL_SECTIONS,
    build_next_week_playbook_block,
    PLAYBOOK_PREFIX,
)
from agent_reach.daily_run.skill_writeback import (
    EXPERIENCE_HEADER,
    build_weekly_experience_block,
    week_section_header,
)


def _sample_report(**overrides: Any) -> dict[str, Any]:
    report: dict[str, Any] = {
        "week_start": "2026-08-10",
        "week_end": "2026-08-14",
        "process_improvements": [],
        "skill_learning": [],
        "weekly_pnl": 0,
        "weekly_pnl_pct": 0,
        "holdings": [],
        "hot_sectors": [],
        "mss_summary": [],
    }
    report.update(overrides)
    return report


def _minimal_skill(report: dict[str, Any] | None = None) -> str:
    report = report or _sample_report()
    lines = list(REQUIRED_SKILL_SECTIONS)
    lines.append(build_next_week_playbook_block(report, []).rstrip())
    lines.append(build_weekly_experience_block(report).rstrip())
    return "\n".join(lines) + "\n"


@pytest.fixture
def fragments_tmp(monkeypatch, tmp_path):
    frag = tmp_path / "skill"
    monkeypatch.setattr("agent_reach.daily_run.skill_fragments.FRAGMENTS_DIR", frag)
    monkeypatch.setattr("agent_reach.daily_run.skill_fragments.PLAYBOOK_FRAGMENT", frag / "playbook.md")
    monkeypatch.setattr("agent_reach.daily_run.skill_fragments.EXPERIENCE_FRAGMENT", frag / "experience_latest.md")
    monkeypatch.setattr("agent_reach.daily_run.skill_fragments.FRAGMENTS_MANIFEST", frag / "fragments.json")
    monkeypatch.setattr("agent_reach.daily_run.skill_fragments.ARCHIVE_DIR", tmp_path / "archives")
    return frag


class TestSkillGates:
    def test_gates_pass_on_minimal_skill(self):
        report = _sample_report()
        result = run_skill_gates(
            _minimal_skill(report),
            report,
            settings={"weekly_report": {"skill_external": {"enabled": False}}},
        )
        assert result["ok"] is True
        assert result.get("block_weekly_push") is False

    def test_gates_fail_missing_section(self):
        report = {"week_start": "2026-08-10", "week_end": "2026-08-14"}
        text = "## only one section\n"
        result = run_skill_gates(text, report)
        assert result["ok"] is False
        assert result["block_weekly_push"] is True
        assert any("缺少必备章节" in f for f in result["failures"])

    def test_gates_fail_max_lines(self):
        report = _sample_report()
        text = _minimal_skill(report) + "\n".join(["padding"] * 500)
        result = run_skill_gates(
            text,
            report,
            settings={"weekly_report": {"skill_gates": {"max_lines": 50}}},
        )
        assert result["ok"] is False
        assert any("行数" in f for f in result["failures"])

    def test_gates_disabled(self):
        result = run_skill_gates(
            "short",
            {},
            settings={"weekly_report": {"skill_gates": {"enabled": False}}},
        )
        assert result["skipped"] is True
        assert gates_enabled({"weekly_report": {"skill_gates": {"enabled": False}}}) is False

    def test_gates_pass_on_canonical_skill(self):
        from agent_reach.daily_run.skill_improvements_apply import (
            build_next_week_playbook_block,
            canonical_skill_path,
        )
        from agent_reach.daily_run.skill_fragments import write_fragments
        from agent_reach.daily_run.skill_writeback import build_weekly_experience_block

        skill_path = canonical_skill_path()
        if not skill_path.exists():
            pytest.skip("canonical skill missing")
        text = skill_path.read_text(encoding="utf-8")
        report = _sample_report(
            process_improvements=[
                {"priority": "medium", "title": "测试", "detail": "d", "action": "a"}
            ],
        )
        write_fragments(
            playbook_block=build_next_week_playbook_block(report, []),
            experience_block=build_weekly_experience_block(report),
            week_start="2026-08-10",
            week_end="2026-08-14",
        )
        result = run_skill_gates(
            text,
            report,
            settings={"weekly_report": {"skill_external": {"enabled": True}}},
        )
        assert result["ok"] is True, result.get("failures")

    def test_gates_fail_fingerprint_mismatch(self, fragments_tmp):
        from agent_reach.daily_run.skill_fragments import write_fragments
        from agent_reach.daily_run.skill_writeback import build_weekly_experience_block

        report = _sample_report()
        write_fragments(
            playbook_block="## 📋 下周执行清单（周六自动更新 · 损坏）\n\n### 🔧 流程改进\n- bad",
            experience_block=build_weekly_experience_block(report),
            week_start="2026-08-10",
            week_end="2026-08-14",
        )
        text = _minimal_skill(report)
        result = run_skill_gates(
            text,
            report,
            settings={"weekly_report": {"skill_external": {"enabled": True}}},
        )
        assert result["ok"] is False
        assert any("playbook" in f and "fingerprint" in f for f in result["failures"])

    def test_format_gate_alert(self):
        md = format_gate_alert_markdown({"ok": False, "failures": ["缺少 playbook"], "warnings": []})
        assert "门禁未通过" in md
        assert "缺少 playbook" in md

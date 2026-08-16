# -*- coding: utf-8
"""Tests for Saturday skill mechanical gates."""

import pytest

from agent_reach.daily_run.skill_gates import (
    format_gate_alert_markdown,
    gates_enabled,
    run_skill_gates,
)
from agent_reach.daily_run.skill_improvements_apply import REQUIRED_SKILL_SECTIONS


def _minimal_skill(week_start: str = "2026-08-10", week_end: str = "2026-08-14") -> str:
    lines = list(REQUIRED_SKILL_SECTIONS)
    lines.extend(
        [
            f"### 📅 {week_start} ~ {week_end} 周复盘（周六自动沉淀）",
            "**情况说明：** 测试",
            "### 🔧 流程改进",
            "- 改进项",
        ]
    )
    return "\n".join(lines) + "\n"


class TestSkillGates:
    def test_gates_pass_on_minimal_skill(self):
        report = {
            "week_start": "2026-08-10",
            "week_end": "2026-08-14",
            "process_improvements": [],
            "skill_learning": [],
        }
        result = run_skill_gates(
            _minimal_skill(),
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
        report = {"week_start": "2026-08-10", "week_end": "2026-08-14"}
        text = _minimal_skill() + "\n".join(["padding"] * 500)
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
        report = {
            "week_start": "2026-08-10",
            "week_end": "2026-08-14",
            "process_improvements": [
                {"priority": "medium", "title": "测试", "detail": "d", "action": "a"}
            ],
            "skill_learning": [],
        }
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

    def test_format_gate_alert(self):
        md = format_gate_alert_markdown({"ok": False, "failures": ["缺少 playbook"], "warnings": []})
        assert "门禁未通过" in md
        assert "缺少 playbook" in md

# -*- coding: utf-8
"""Tests for external skill fragments."""

from pathlib import Path

import pytest

from agent_reach.daily_run.skill_fragments import (
    annotate_experience_fragment,
    external_enabled,
    write_fragments,
)
from agent_reach.daily_run.skill_improvements_apply import (
    build_next_week_playbook_block,
    patch_canonical_skill_sections,
)
from agent_reach.daily_run.skill_writeback import build_weekly_experience_block


@pytest.fixture
def fragments_tmp(monkeypatch, tmp_path):
    frag = tmp_path / "skill"
    monkeypatch.setattr("agent_reach.daily_run.skill_fragments.FRAGMENTS_DIR", frag)
    monkeypatch.setattr("agent_reach.daily_run.skill_fragments.PLAYBOOK_FRAGMENT", frag / "playbook.md")
    monkeypatch.setattr("agent_reach.daily_run.skill_fragments.EXPERIENCE_FRAGMENT", frag / "experience_latest.md")
    monkeypatch.setattr("agent_reach.daily_run.skill_fragments.FRAGMENTS_MANIFEST", frag / "fragments.json")
    monkeypatch.setattr("agent_reach.daily_run.skill_fragments.ARCHIVE_DIR", tmp_path / "archives")
    return frag


class TestSkillFragments:
    def test_external_enabled_default(self):
        assert external_enabled({}) is True
        assert external_enabled({"weekly_report": {"skill_external": {"enabled": False}}}) is False

    def test_write_fragments(self, fragments_tmp):
        report = {
            "week_start": "2026-08-10",
            "week_end": "2026-08-14",
            "weekly_pnl": 100,
            "weekly_pnl_pct": 0.1,
            "holdings": [],
            "hot_sectors": [],
            "mss_summary": [],
        }
        manifest = write_fragments(
            playbook_block=build_next_week_playbook_block(report, ["a → b"]),
            experience_block=build_weekly_experience_block(report),
            week_start="2026-08-10",
            week_end="2026-08-14",
            refinement_id="refine_0001",
        )
        assert (fragments_tmp / "playbook.md").exists()
        assert (fragments_tmp / "experience_latest.md").exists()
        assert "refine_0001" == manifest["refinement_id"]
        pb_text = (fragments_tmp / "playbook.md").read_text(encoding="utf-8")
        assert "流程改进" in pb_text or "下周执行清单" in pb_text

    def test_patch_canonical_external(self, fragments_tmp, tmp_path, monkeypatch):
        skill = tmp_path / "daily_run_skill.md"
        skill.write_text(
            "\n".join(
                [
                    "## ⚡ Agent 执行入口",
                    "## 📋 下周执行清单（周六自动更新 · old）",
                    "old body",
                    "## 🧠 股票大师实战经验沉淀库 (每日收盘更新)",
                    "old exp",
                    "## 🛠️ 运维与排障指南",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.skill_improvements_apply.canonical_skill_path",
            lambda: skill,
        )
        report = {
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
        result = patch_canonical_skill_sections(
            report,
            [],
            settings={"weekly_report": {"skill_external": {"enabled": True}}},
        )
        assert result["external"] is True
        assert (fragments_tmp / "playbook.md").exists()
        text = skill.read_text(encoding="utf-8")
        assert "playbook.md" in text
        assert "old body" not in text

    def test_annotate_experience_fragment(self, fragments_tmp):
        write_fragments(
            playbook_block="pb",
            experience_block="### 📅 2026-08-10 ~ 2026-08-14 周复盘（周六自动沉淀）\n* x\n",
            week_start="2026-08-10",
            week_end="2026-08-14",
        )
        changed = annotate_experience_fragment(
            week_start="2026-08-10",
            week_end="2026-08-14",
            refinement_id="refine_0002",
        )
        assert changed is True
        exp_text = (fragments_tmp / "experience_latest.md").read_text(encoding="utf-8")
        assert "refine_0002" in exp_text

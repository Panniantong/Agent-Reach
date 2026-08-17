# -*- coding: utf-8
"""Tests for weekly skill closure: settings apply + playbook + sync."""

from pathlib import Path
from unittest.mock import patch

from agent_reach.daily_run.skill_improvements_apply import (
    PLAYBOOK_PREFIX,
    apply_settings_from_improvements,
    apply_weekly_skill_closure,
    build_next_week_playbook_block,
    patch_playbook_section,
)


class TestSkillImprovementsApply:
    def test_apply_settings_from_improvements(self):
        report = {
            "process_improvements": [
                {
                    "category": "mss",
                    "priority": "high",
                    "title": "本周 3 次 MSS 预测未命中",
                    "action": "增大 mss_forecast.base_spread",
                },
                {
                    "category": "schedule",
                    "priority": "high",
                    "title": "缺失 2 天收盘复盘",
                    "action": "检查 cron",
                },
            ]
        }
        settings = {
            "mss_forecast": {"base_spread": 8},
            "schedule": {"alert_after_consecutive_failures": 3},
            "harness": {"threshold_evolution_mode": "fixed"},
        }
        new_settings, applied = apply_settings_from_improvements(report, settings)
        assert new_settings["mss_forecast"]["base_spread"] == 9
        assert new_settings["schedule"]["alert_after_consecutive_failures"] == 2
        assert len(applied) == 2

    def test_build_next_week_playbook_block(self):
        block = build_next_week_playbook_block(
            {
                "week_start": "2026-07-20",
                "week_end": "2026-07-24",
                "process_improvements": [
                    {
                        "priority": "high",
                        "title": "缺失收盘",
                        "detail": "经验沉淀中断",
                        "action": "补跑 close",
                    }
                ],
                "skill_learning": [
                    {"title": "backtest", "summary": "学习回测", "action": "daily-run backtest"},
                ],
            },
            ["mss_forecast.base_spread: 8 → 9"],
        )
        assert PLAYBOOK_PREFIX in block
        assert "参数自动调整" in block
        assert "缺失收盘" in block
        assert "backtest" in block

    def test_patch_playbook_section(self, tmp_path: Path):
        path = tmp_path / "SKILL.md"
        path.write_text(
            "# skill\n\n## old\n\n## 🛠️ 运维\n",
            encoding="utf-8",
        )
        block = build_next_week_playbook_block(
            {"week_start": "2026-07-20", "week_end": "2026-07-24", "process_improvements": []},
            [],
        )
        assert patch_playbook_section(path, block) is True
        text = path.read_text(encoding="utf-8")
        assert PLAYBOOK_PREFIX in text
        assert "## 🛠️ 运维" in text

    @patch("agent_reach.daily_run.skill_improvements_apply.ensure_runtime_updated", return_value={"steps": ["pip_install_editable"]})
    @patch("agent_reach.daily_run.skill_improvements_apply.audit_weekly_skill", return_value={"ok": True, "fixes": []})
    @patch("agent_reach.daily_run.skill_improvements_apply.sync_canonical_skill_to_local", return_value=["/tmp/SKILL.md"])
    @patch("agent_reach.daily_run.skill_improvements_apply.patch_canonical_skill_sections", return_value={"experience": True, "playbook": True})
    @patch("agent_reach.daily_run.skill_improvements_apply.save_user_settings")
    def test_apply_weekly_skill_closure(self, mock_save, mock_patch, mock_sync, mock_audit, mock_runtime, tmp_path: Path):
        mock_save.return_value = tmp_path / "settings.json"
        result = apply_weekly_skill_closure(
            {
                "week_start": "2026-07-20",
                "week_end": "2026-07-24",
                "process_improvements": [
                    {
                        "category": "mss",
                        "priority": "high",
                        "title": "MSS miss",
                        "action": "base_spread",
                    }
                ],
                "skill_learning": [],
            },
            {
                "weekly_report": {"skill_writeback": True, "skill_auto_apply_settings": True},
                "harness": {"threshold_evolution_mode": "fixed"},
            },
        )
        assert result["skipped"] is False
        assert result["synced_skills"] == ["/tmp/SKILL.md"]
        assert result["skill_audit"]["ok"] is True
        mock_audit.assert_called_once()
        mock_save.assert_called_once()

    def test_optimize_skill_markdown_dedupes_h2(self, tmp_path: Path):
        from agent_reach.daily_run.skill_improvements_apply import optimize_skill_markdown

        raw = "# t\n\n## A\none\n\n## B\ntwo\n\n## A\nthree\n"
        out, fixes = optimize_skill_markdown(raw)
        assert "dedupe_h2_sections" in fixes
        assert out.count("## A") == 1
        assert "three" not in out

    def test_audit_weekly_skill(self, tmp_path: Path, monkeypatch):
        from agent_reach.daily_run.skill_improvements_apply import audit_weekly_skill

        skill = tmp_path / "daily_run_skill.md"
        skill.write_text(
            "\n".join(
                [
                    "## ⚡ Agent 执行入口",
                    "## 📋 下周执行清单（周六自动更新 · x）",
                    "## 🛡️ Phase-1 质量工程化",
                    "## 📊 决策模型",
                    "## 🧠 股票大师实战经验沉淀库 (每日收盘更新)",
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
        monkeypatch.setattr(
            "agent_reach.daily_run.skill_improvements_apply.sync_canonical_skill_to_local",
            lambda settings=None: [],
        )
        result = audit_weekly_skill({})
        assert result["ok"] is True

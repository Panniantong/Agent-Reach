# -*- coding: utf-8
"""Tests for Saturday weekly skill writeback."""

from pathlib import Path

from agent_reach.daily_run.skill_improvements_apply import write_weekly_skill_experience
from agent_reach.daily_run.skill_writeback import (
    build_weekly_experience_block,
    patch_skill_file,
    week_section_header,
)


SAMPLE_SKILL = """# skill

## 🧠 股票大师实战经验沉淀库 (每日收盘更新)

本库用于记录每日收盘后的实战得失，并将经验提炼为量化规则，动态更新以指导后续交易。

### 📅 2026-07-06 (周一) 经验沉淀 — old entry
* old content

---

## 🛠️ 运维与排障指南

help
"""


class TestSkillWriteback:
    def test_build_weekly_experience_block(self):
        block = build_weekly_experience_block(
            {
                "week_start": "2026-07-20",
                "week_end": "2026-07-24",
                "harness_refinement_id": "refine_0003",
                "weekly_pnl": 1200.5,
                "weekly_pnl_pct": 1.2,
                "start_total": 87000,
                "end_total": 88200.5,
                "realized_pnl": -100,
                "holdings": [{"name": "澜起科技", "code": "688008", "change_pct": 3.6}],
                "hot_sectors": [{"name": "澜起科技", "change_pct": 3.6}],
                "trades": [{"side": "buy"}],
                "mss_summary": [{"job": "morning"}, {"job": "close"}],
                "experience_snippets": ["2026-07-24 澜起 MSS=48 ✅"],
                "process_improvements": [
                    {
                        "priority": "high",
                        "title": "缺失收盘",
                        "action": "补跑 close",
                    }
                ],
                "skill_learning": [
                    {"title": "backtest", "summary": "学习回测命令"},
                ],
            }
        )
        assert "2026-07-20 ~ 2026-07-24" in block
        assert "refine_0003" in block
        assert "情况说明" in block
        assert "持仓浮盈合计" in block
        assert "缺失收盘" in block
        assert "backtest" in block

    def test_patch_skill_file_insert_and_replace(self, tmp_path: Path):
        path = tmp_path / "SKILL.md"
        path.write_text(SAMPLE_SKILL, encoding="utf-8")
        block = build_weekly_experience_block(
            {
                "week_start": "2026-07-20",
                "week_end": "2026-07-24",
                "weekly_pnl": 0,
                "weekly_pnl_pct": 0,
                "holdings": [],
                "hot_sectors": [],
                "trades": [],
                "mss_summary": [],
            }
        )
        assert patch_skill_file(path, block, "2026-07-20", "2026-07-24") is True
        text = path.read_text(encoding="utf-8")
        assert week_section_header("2026-07-20", "2026-07-24") in text
        assert text.index("2026-07-20 ~ 2026-07-24") < text.index("2026-07-06")

        block2 = block.replace("持平", "盈利")
        assert patch_skill_file(path, block2, "2026-07-20", "2026-07-24") is True
        updated = path.read_text(encoding="utf-8")
        assert updated.count("2026-07-20 ~ 2026-07-24") == 1
        assert "盈利" in updated

    def test_write_weekly_skill_experience_disabled(self):
        result = write_weekly_skill_experience(
            {"week_start": "2026-07-20", "week_end": "2026-07-24"},
            {"weekly_report": {"skill_writeback": False}},
        )
        assert result["skipped"] is True

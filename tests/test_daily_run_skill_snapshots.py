# -*- coding: utf-8
"""Snapshot-style regression tests for weekly skill writeback blocks."""

from agent_reach.daily_run.skill_improvements_apply import build_next_week_playbook_block
from agent_reach.daily_run.skill_writeback import build_weekly_experience_block

SAMPLE_REPORT = {
    "week_start": "2026-08-10",
    "week_end": "2026-08-14",
    "weekly_pnl": -788.0,
    "weekly_pnl_pct": -0.9,
    "start_total": 85623.27,
    "end_total": 86077.27,
    "holdings": [{"name": "澜起科技", "code": "688008", "change_pct": 0.8}],
    "hot_sectors": [{"name": "水晶光电", "change_pct": 2.45}],
    "mss_summary": [{"job": "morning"}, {"job": "close", "mss": 31.0}],
    "experience_snippets": ["2026-08-14 澜起科技 MSS=31.3 ✅ 宏观一票否决"],
    "process_improvements": [
        {
            "priority": "medium",
            "title": "盘中扫描偏少",
            "detail": "intraday 次数 <5",
            "action": "检查 cron",
        }
    ],
    "skill_learning": [{"title": "Kronos", "summary": "周日 forecast 参考 Phase-2.5"}],
    "notes": [],
}


class TestSkillWritebackSnapshots:
    def test_experience_block_snapshot_lines(self):
        block = build_weekly_experience_block(SAMPLE_REPORT)
        assert "### 📅 2026-08-10 ~ 2026-08-14 周复盘（周六自动沉淀）" in block
        assert "**情况说明：**" in block
        assert "盘中扫描偏少" in block
        assert "Kronos" in block
        assert block.count("2026-08-10 ~ 2026-08-14") == 1

    def test_playbook_block_snapshot_lines(self):
        block = build_next_week_playbook_block(
            SAMPLE_REPORT,
            ["mss_forecast.base_spread: 8 → 9"],
        )
        assert "## 📋 下周执行清单（周六自动更新" in block
        assert "参数自动调整" in block
        assert "盘中扫描偏少" in block
        assert "mss_forecast.base_spread" in block

    def test_playbook_block_max_lines(self):
        block = build_next_week_playbook_block(SAMPLE_REPORT, [])
        assert len(block.splitlines()) < 40

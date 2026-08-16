# -*- coding: utf-8
"""Tests for skill archive / compaction helpers."""

from pathlib import Path

from agent_reach.daily_run.skill_archive import (
    annotate_experience_refinement_id,
    compact_experience_sections,
)
from agent_reach.daily_run.skill_learning import (
    dedupe_skill_learning_items,
    filter_superseded_skill_learning,
)
from agent_reach.daily_run.skill_writeback import week_section_header


SAMPLE = """# skill

## 🧠 股票大师实战经验沉淀库

### 📅 2026-08-03 ~ 2026-08-07 周复盘（周六自动沉淀）
old week 1

---

### 📅 2026-08-10 ~ 2026-08-14 周复盘（周六自动沉淀）
old week 2

---

### 📅 2026-08-17 ~ 2026-08-21 周复盘（周六自动沉淀）
newest week

---
"""


class TestSkillArchive:
    def test_compact_keeps_newest_weeks(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.skill_archive._ARCHIVE_DIR",
            tmp_path / "archives",
        )
        out, archived = compact_experience_sections(
            SAMPLE,
            settings={"weekly_report": {"skill_archive_keep_weeks": 1}},
        )
        assert "2026-08-17 ~ 2026-08-21" in out
        assert "2026-08-03 ~ 2026-08-07" not in out
        assert len(archived) == 2

    def test_annotate_refinement_id(self):
        text = SAMPLE.replace("newest week", "newest week\n")
        out = annotate_experience_refinement_id(
            text,
            week_start="2026-08-17",
            week_end="2026-08-21",
            refinement_id="refine_0007",
        )
        assert "`refine_0007`" in out
        assert week_section_header("2026-08-17", "2026-08-21") in out


class TestSkillLearningDedupe:
    def test_dedupe_skill_learning_items(self):
        items = [
            {"title": "Kronos", "summary": "a"},
            {"title": "kronos", "summary": "b"},
        ]
        out = dedupe_skill_learning_items(items)
        assert len(out) == 1
        assert out[0]["summary"] == "b"

    def test_filter_superseded(self):
        new_items = [{"title": "backtest", "summary": "x"}]
        out = filter_superseded_skill_learning(new_items, ["backtest"])
        assert out == []

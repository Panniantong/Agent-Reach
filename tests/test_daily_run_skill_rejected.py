# -*- coding: utf-8
"""Tests for rejected strategy guardrails."""

from agent_reach.daily_run.skill_improvements_apply import _normalize_report_for_writeback
from agent_reach.daily_run.skill_rejected import (
    add_rejected_strategy,
    filter_rejected_items,
    is_rejected_title,
)


class TestSkillRejected:
    def test_filter_rejected_items(self, tmp_path, monkeypatch):
        path = tmp_path / "rejected_strategies.jsonl"
        monkeypatch.setattr("agent_reach.daily_run.skill_rejected._REJECTED_PATH", path)
        add_rejected_strategy("加大 base_spread", "曾导致 MSS 过宽", week_start="2026-08-10", week_end="2026-08-14")
        assert is_rejected_title("加大 base_spread")
        kept, blocked = filter_rejected_items(
            [{"title": "加大 base_spread", "detail": "retry"}, {"title": "新策略", "detail": "ok"}]
        )
        assert len(kept) == 1
        assert kept[0]["title"] == "新策略"
        assert blocked == ["加大 base_spread"]

    def test_normalize_report_filters_rejected(self, tmp_path, monkeypatch):
        path = tmp_path / "rejected_strategies.jsonl"
        monkeypatch.setattr("agent_reach.daily_run.skill_rejected._REJECTED_PATH", path)
        add_rejected_strategy("bad idea", "failed backtest")
        out = _normalize_report_for_writeback(
            {
                "process_improvements": [{"title": "bad idea", "detail": "x"}],
                "skill_learning": [],
            }
        )
        assert out["process_improvements"] == []
        assert "bad idea" in (out.get("_rejected_blocked") or [])

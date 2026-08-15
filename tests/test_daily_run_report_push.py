# -*- coding: utf-8
"""Tests for split Feishu push (morning / close)."""

from unittest.mock import patch

from agent_reach.daily_run.report_push import (
    push_report_sections,
    render_close_sections,
    render_morning_sections,
    split_push_enabled,
)
from agent_reach.daily_run.settings import load_settings


class TestReportPush:
    def test_render_morning_sections(self):
        sections = render_morning_sections(
            team_markdown="**Team**",
            report_markdown="**Decision**",
            report={"name": "澜起", "verdict": "可做"},
        )
        assert len(sections) == 2
        assert sections[0].category == "experts"
        assert sections[0].title == "🌅 早盘 1/2 · 专家共识 · 澜起"
        assert sections[1].category == "decision"
        assert "2/2" in sections[1].title
        assert "可做" in sections[1].title

    def test_render_close_sections_skips_empty(self):
        sections = render_close_sections(
            verify_name="澜起",
            market_markdown="**Market**",
            verify_markdown="**验证**",
        )
        assert len(sections) == 2
        assert sections[0].category == "close_market"
        assert sections[1].category == "verify"

    def test_render_close_sections_empty_market(self):
        sections = render_close_sections(
            verify_name="澜起",
            verify_markdown="**验证**",
        )
        assert len(sections) == 1
        assert sections[0].category == "verify"

    def test_split_push_enabled(self):
        cfg = {"report": {"split_push": True, "morning_split_push": False}}
        assert split_push_enabled(cfg, report_kind="morning") is False
        assert split_push_enabled(cfg, report_kind="close") is True

    @patch("agent_reach.integrations.feishu.send_card")
    def test_push_report_sections_split(self, mock_send):
        mock_send.return_value = {"code": 0}
        settings = load_settings()
        settings.setdefault("report", {})["split_push"] = True
        settings["report"]["split_push_interval_seconds"] = 0
        sections = render_morning_sections(
            team_markdown="A",
            report_markdown="B",
            report={"name": "X", "verdict": "观察"},
        )
        out = push_report_sections(
            sections,
            settings=settings,
            config=None,
            report_type="premarket",
            fallback_title="test",
            split=True,
        )
        assert out["mode"] == "split"
        assert out["count"] == 2
        assert mock_send.call_count == 2

    @patch("agent_reach.integrations.feishu.send_card")
    def test_push_report_sections_single_when_disabled(self, mock_send):
        mock_send.return_value = {"code": 0}
        settings = load_settings()
        sections = render_morning_sections(
            team_markdown="A",
            report_markdown="B",
            report={"name": "X", "verdict": "观察"},
        )
        out = push_report_sections(
            sections,
            settings=settings,
            config=None,
            report_type="premarket",
            fallback_title="test",
            split=False,
        )
        assert out["mode"] == "single"
        assert mock_send.call_count == 1

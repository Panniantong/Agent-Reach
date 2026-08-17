# -*- coding: utf-8
"""Tests for report LLM narrative cards."""

from unittest.mock import patch

from agent_reach.daily_run.report_narrative import (
    generate_close_narrative,
    generate_morning_narrative,
    generate_weekly_narrative,
    render_narrative_markdown,
)
from agent_reach.daily_run.report_push import render_close_sections, render_morning_sections
from agent_reach.daily_run.weekly_report import WeeklyReport, render_weekly_sections


def test_morning_narrative_deterministic():
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_morning_narrative(
            {"name": "澜起科技", "code": "688008", "portfolio": {"cash_ratio": 0.46}},
            {"name": "澜起科技", "verdict": "回避", "mss_final": 30.4},
            settings={"llm_narrative": {"enabled": True}},
        )
    assert narrative["planner"] == "deterministic"
    md = render_narrative_markdown(narrative, job="morning")
    assert "决策摘要" in md


def test_morning_sections_include_ai_last():
    sections = render_morning_sections(
        team_markdown="",
        report_markdown="**MSS**",
        report={"name": "澜起科技", "verdict": "回避"},
        narrative={
            "summary": "测试早报",
            "focus_points": ["A"],
            "planner": "llm",
            "job": "morning",
        },
    )
    assert sections[-1].category == "ai_narrative"
    assert "测试早报" in sections[-1].body


def test_close_sections_include_ai_last():
    sections = render_close_sections(
        verify_name="澜起科技",
        verify_markdown="verify",
        narrative={"summary": "收盘测试", "focus_points": ["B"], "job": "close"},
    )
    assert sections[-1].category == "ai_narrative"


def test_weekly_sections_include_ai_last():
    report = WeeklyReport(
        week_start=__import__("datetime").date(2026, 8, 10),
        week_end=__import__("datetime").date(2026, 8, 14),
        start_total=100000,
        end_total=99212,
        weekly_pnl=-788,
        weekly_pnl_pct=-0.9,
        realized_pnl=0,
        llm_narrative={"summary": "周报测试", "focus_points": ["C"], "job": "weekly"},
    )
    sections = render_weekly_sections(report)
    assert sections[-1].label == "AI解读"


def test_weekly_narrative_with_pnl():
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_weekly_narrative(
            {
                "week_start": "2026-08-10",
                "week_end": "2026-08-14",
                "weekly_pnl": -788,
                "weekly_pnl_pct": -0.9,
                "stock_pnl": -788,
                "cash_pnl": 0,
            },
            settings={"llm_narrative": {"enabled": True}},
        )
    assert "-788" in narrative["summary"] or "788" in " ".join(narrative.get("focus_points") or [])


def test_close_narrative_recommendations():
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_close_narrative(
            snapshot={"name": "澜起科技"},
            verify={"recommendations": ["维持高现金"], "summary": "宏观否决"},
            portfolio_summary={"daily_pnl": -90, "daily_pnl_pct": -0.1},
            settings={"llm_narrative": {"enabled": True}},
        )
    joined = " ".join(narrative.get("focus_points") or [])
    assert "维持高现金" in joined or "宏观否决" in narrative.get("summary", "")

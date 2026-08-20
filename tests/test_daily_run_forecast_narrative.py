# -*- coding: utf-8
"""Tests for forecast LLM narrative layer."""

from unittest.mock import patch

from agent_reach.daily_run.forecast_narrative import (
    build_narrative_context,
    generate_forecast_narrative,
    render_forecast_narrative_markdown,
)
from agent_reach.daily_run.week_forecast import ForecastSection, render_forecast_sections


def test_build_narrative_context_includes_divergence():
    ctx = build_narrative_context(
        {
            "week_start": "2026-08-17",
            "week_end": "2026-08-21",
            "symbols": {
                "300308": {
                    "name": "中际旭创",
                    "role": "holding",
                    "kronos": {"available": True, "cum_change_pct": 2.5, "direction_nd": "up"},
                    "kronos_divergence_days": ["2026-08-18"],
                    "days": {"2026-08-18": {"expected_change_pct": 0.5}},
                }
            },
            "notes": ["Kronos 路径预测 1/1 只"],
        }
    )
    assert ctx["symbols"][0]["divergence_days"] == ["2026-08-18"]


def test_deterministic_narrative_when_no_llm():
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_forecast_narrative(
            {
                "week_start": "2026-08-17",
                "week_end": "2026-08-21",
                "symbols": {
                    "600584": {
                        "name": "长电科技",
                        "kronos": {"available": True, "cum_change_pct": -2.0},
                        "days": {},
                    }
                },
                "notes": [],
                "calibration_used": {"hit_rate": 0.4},
            },
            settings={"week_forecast": {"llm_narrative": {"enabled": True}}},
        )
    assert narrative["planner"] == "deterministic"
    assert "长电科技" in " ".join(narrative.get("focus_points") or [])


@patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value="deepseek")
@patch(
    "agent_reach.daily_run.llm_chat.chat_json",
    return_value={
        "summary": "下周偏防守",
        "focus_points": ["关注 Kronos 偏弱标的"],
        "divergence_notes": [],
        "risk_alerts": ["维持高现金"],
    },
)
def test_llm_narrative(mock_chat, mock_provider):
    narrative = generate_forecast_narrative(
        {"week_start": "2026-08-17", "week_end": "2026-08-21", "symbols": {}, "notes": []},
        settings={"week_forecast": {"llm_narrative": {"enabled": True, "provider": "deepseek", "planner": "llm"}}},
    )
    assert narrative["planner"] == "llm"
    md = render_forecast_narrative_markdown(narrative)
    assert "规则解读" in md
    assert "下周偏防守" in md


def test_render_forecast_sections_puts_ai_last():
    sections = render_forecast_sections(
        {
            "week_start": "2026-08-17",
            "week_end": "2026-08-21",
            "llm_narrative": {
                "summary": "测试总览",
                "focus_points": ["A"],
                "planner": "llm",
            },
            "mss_daily": {},
            "symbols": {},
            "news_events": [],
        }
    )
    assert sections[-1].label == "规则解读"
    assert isinstance(sections[-1], ForecastSection)

# -*- coding: utf-8
"""Tests for report LLM narrative cards."""

import json
from unittest.mock import patch

from agent_reach.daily_run.report_narrative import (
    _compact_context,
    _compact_narrative_payload,
    _narrative_limits,
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


def test_narrative_compact_limits():
    limits = _narrative_limits({})
    payload = _compact_narrative_payload(
        {
            "summary": "x" * 100,
            "focus_points": [f"p{i}" for i in range(6)],
            "divergence_notes": ["d1", "d2", "d3"],
            "risk_alerts": ["r1", "r2", "r3"],
        },
        limits,
    )
    assert len(payload["summary"]) <= limits["max_summary_chars"] + 1
    assert len(payload["focus_points"]) <= limits["max_focus_points"]
    assert len(payload["risk_alerts"]) <= limits["max_risk_alerts"]


def test_compact_context_strips_heavy_fields():
    limits = _narrative_limits({"max_context_chars": 400})
    ctx = _compact_context(
        {
            "job": "morning",
            "mss_breakdown": {"fx": 1, "flow": 2, "technical": 3},
            "experience_snippets": ["a" * 200],
            "summary": "测试",
        },
        limits,
    )
    assert "mss_breakdown" not in ctx or len(json.dumps(ctx, ensure_ascii=False)) <= 500


def test_render_narrative_markdown_is_concise():
    md = render_narrative_markdown(
        {
            "summary": "总览一句",
            "focus_points": ["A", "B"],
            "risk_alerts": ["R"],
            "planner": "llm",
            "job": "morning",
        },
        job="morning",
    )
    assert "关注点" in md
    assert "解读来源" not in md


def test_intraday_narrative_deterministic_from_scan():
    from agent_reach.daily_run.report_narrative import generate_intraday_narrative

    scan_result = {
        "scan": {"scan_id": "S5", "name": "澜起科技", "code": "688008", "mss_final": 46.7, "verdict": "观察"},
        "lookback_mss": 47.16,
        "trend": "falling",
        "evaluation": {"report": {"reasoning": "MSS 低于进攻阈值，维持观望"}},
        "lookback_detail": [{"scan_id": "S5", "mss_final": 46.7, "weight": 0.5}],
    }
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_intraday_narrative(
            scan_result=scan_result,
            settings={"llm_narrative": {"enabled": True}},
        )
    assert narrative["planner"] == "deterministic"
    assert "S5" in narrative["summary"]
    assert "46.7" in narrative["summary"] or "47.16" in " ".join(narrative.get("focus_points") or [])


def test_merged_intraday_narrative_deterministic():
    from agent_reach.daily_run.report_narrative import generate_merged_intraday_narrative

    symbol_results = [
        {
            "code": "688008",
            "name": "澜起科技",
            "result": {
                "scan": {
                    "scan": {"scan_id": "S5", "mss_final": 46.7, "verdict": "观察"},
                    "lookback_mss": 47.0,
                    "trend": "falling",
                },
                "trade": {"decision": {"action": "hold", "reasoning": "维持观望", "friction_blocked": True}},
            },
        },
        {
            "code": "002273",
            "name": "水晶光电",
            "result": {
                "scan": {
                    "scan": {"scan_id": "S5", "mss_final": 49.6, "verdict": "观察"},
                    "lookback_mss": 49.0,
                    "trend": "rising",
                },
                "trade": {"decision": {"action": "hold", "friction_blocked": True}},
            },
        },
    ]
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_merged_intraday_narrative(
            symbol_results,
            scan_id="S5",
            settings={"llm_narrative": {"enabled": True}},
        )
    assert narrative["planner"] == "deterministic"
    assert "S5" in narrative["summary"]
    assert "2" in narrative["summary"] or "2" in " ".join(narrative.get("focus_points") or [])
    assert len(narrative.get("risk_alerts") or []) == 1
    assert "等2只" in narrative["risk_alerts"][0] or "澜起科技" in narrative["risk_alerts"][0]
    assert "摩擦惩罚阻断" in narrative["risk_alerts"][0]


def test_merge_duplicate_risk_alerts():
    from agent_reach.daily_run.report_narrative import _merge_duplicate_risk_alerts

    merged = _merge_duplicate_risk_alerts(
        [
            "澜起科技 摩擦惩罚阻断",
            "水晶光电 摩擦惩罚阻断",
            "海能达 摩擦惩罚阻断",
            "中际旭创 MSS 低于 macro_veto 区间",
        ]
    )
    assert len(merged) == 2
    assert "等3只：摩擦惩罚阻断" in merged[0] or "澜起科技、水晶光电、海能达：摩擦惩罚阻断" in merged[0]
    assert "中际旭创" in merged[1]


def test_merged_morning_narrative_deterministic():
    from agent_reach.daily_run.report_narrative import generate_merged_morning_narrative

    entries = [
        ("澜起科技", "688008", {"verdict": "观察", "mss_final": 42.5}),
        ("水晶光电", "002273", {"verdict": "观察", "mss_final": 40.0}),
    ]
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_merged_morning_narrative(
            entries,
            primary_snapshot={"portfolio": {"cash_ratio": 0.46}},
            settings={"llm_narrative": {"enabled": True}},
        )
    assert narrative["planner"] == "deterministic"
    assert "2只" in narrative["summary"] or "2只" in " ".join(narrative.get("focus_points") or [])


def test_merged_close_narrative_uses_portfolio_pnl():
    from agent_reach.daily_run.report_narrative import generate_merged_close_narrative

    symbol_results = [
        {
            "code": "688008",
            "name": "澜起科技",
            "result": {"verify": {"summary": "宏观否决"}, "snapshot": {"name": "澜起科技"}},
        }
    ]
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_merged_close_narrative(
            symbol_results,
            portfolio_summary={"daily_pnl": -90, "daily_pnl_pct": -0.1},
            settings={"llm_narrative": {"enabled": True}},
        )
    joined = " ".join(narrative.get("focus_points") or []) + narrative.get("summary", "")
    assert "90" in joined or "盈亏" in joined


def test_close_narrative_includes_trade_operations():
    from agent_reach.daily_run.report_narrative import generate_close_narrative, render_narrative_markdown

    portfolio_summary = {
        "daily_pnl": 1200.0,
        "daily_pnl_pct": 0.6,
        "realized_pnl": 3496.54,
        "trades": [
            {
                "at": "2026-08-19T01:02:56+00:00",
                "decision_action": "sell",
                "actions": [
                    {
                        "side": "sell",
                        "code": "600584",
                        "name": "长电科技",
                        "shares": 800,
                        "price": 85.42,
                        "amount": 68336.0,
                        "commission": 102.5,
                        "realized_pnl": 3496.54,
                        "realized_pnl_pct": 5.4,
                    }
                ],
            }
        ],
    }
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_close_narrative(
            snapshot={"name": "组合"},
            verify={"summary": "宏观否决", "recommendations": ["维持高现金"]},
            portfolio_summary=portfolio_summary,
            settings={"llm_narrative": {"enabled": True}},
        )
    md = render_narrative_markdown(narrative, job="close")
    assert "当日买卖" in md
    assert "长电科技" in md
    assert "800股" in md
    assert "85.42" in md
    assert "3497" in md.replace(",", "") or "3496" in md.replace(",", "")
    assert any("成交" in item for item in narrative.get("focus_points") or [])


def test_format_trade_operation_line_buy_and_sell():
    from agent_reach.daily_run.close_portfolio_summary import format_trade_operation_line

    buy = format_trade_operation_line(
        {
            "side": "buy",
            "name": "长电科技",
            "code": "600584",
            "shares": 800,
            "price": 80.8,
            "amount": 64640.0,
            "commission": 96.96,
            "time": "2026-08-17 09:54",
        }
    )
    assert "买入" in buy
    assert "800股" in buy
    assert "80.80" in buy
    assert "64640" in buy.replace(",", "")

    sell = format_trade_operation_line(
        {
            "side": "sell",
            "name": "京东方A",
            "code": "000725",
            "shares": 1400,
            "price": 6.47,
            "amount": 9058.0,
            "commission": 13.59,
            "realized_pnl": -1471.34,
            "realized_pnl_pct": -13.99,
        }
    )
    assert "卖出" in sell
    assert "1400股" in sell
    assert "1471" in sell.replace(",", "")


def test_append_merged_narrative_section():
    from agent_reach.daily_run.report_push import ReportSection, append_merged_narrative_section

    sections = [ReportSection("decision", "t", "body")]
    out = append_merged_narrative_section(
        sections,
        {"summary": "组合总览", "focus_points": ["A"], "job": "morning"},
        report_kind="morning",
        symbol_count=2,
    )
    assert out[-1].category == "ai_narrative"
    assert "2只" in out[-1].title


def test_persist_and_load_morning_narrative(tmp_path, monkeypatch):
    from agent_reach.daily_run.report_narrative import (
        load_today_morning_narrative,
        persist_morning_narrative,
        render_morning_narrative_footer,
    )

    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(
        "agent_reach.daily_run.report_narrative._morning_narrative_cache_path",
        lambda d=None: cache_dir / "morning_narrative_2026-08-19.json",
    )

    narrative = {
        "summary": "早盘全持仓 10 只",
        "focus_points": ["主导结论 观察"],
        "divergence_notes": [],
        "risk_alerts": [],
        "planner": "deterministic",
        "skipped": False,
        "job": "morning",
    }
    persist_morning_narrative(narrative)
    loaded = load_today_morning_narrative({})
    assert loaded is not None
    assert loaded["summary"] == narrative["summary"]

    footer = render_morning_narrative_footer({})
    assert "AI 解读" in footer
    assert "决策摘要" in footer
    assert footer.startswith("\n\n---\n\n")

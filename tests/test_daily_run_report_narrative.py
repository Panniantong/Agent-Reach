# -*- coding: utf-8
"""Tests for report LLM narrative cards."""

import json
from unittest.mock import patch

from agent_reach.daily_run.report_narrative import (
    _compact_context,
    _compact_narrative_payload,
    _narrative_limits,
    build_close_context,
    build_morning_context,
    generate_close_narrative,
    generate_merged_morning_narrative,
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
    assert "规则解读" in md
    assert "决策摘要" in md


def test_planner_deterministic_skips_llm_even_with_provider():
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value="deepseek"):
        with patch("agent_reach.daily_run.llm_chat.chat_json") as mock_chat:
            narrative = generate_morning_narrative(
                {"name": "澜起科技", "code": "688008", "portfolio": {"cash_ratio": 0.46}},
                {"name": "澜起科技", "verdict": "回避", "mss_final": 30.4},
                settings={"llm_narrative": {"enabled": True, "planner": "deterministic"}},
            )
            mock_chat.assert_not_called()
            assert narrative["planner"] == "deterministic"


def test_per_job_planner_override_keeps_weekly_deterministic():
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value="deepseek"):
        with patch("agent_reach.daily_run.llm_chat.chat_json") as mock_chat:
            mock_chat.return_value = {
                "summary": "LLM 周报",
                "focus_points": ["A"],
                "divergence_notes": [],
                "risk_alerts": [],
            }
            narrative = generate_weekly_narrative(
                {"week_start": "2026-08-10", "week_end": "2026-08-14", "weekly_pnl": -100},
                settings={
                    "llm_narrative": {
                        "enabled": True,
                        "planner": "llm",
                        "jobs": {"weekly": {"planner": "deterministic"}},
                    }
                },
            )
            mock_chat.assert_not_called()
            assert narrative["planner"] == "deterministic"


@patch("agent_reach.daily_run.llm_chat.chat_json")
@patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value="deepseek")
def test_morning_uses_llm_when_planner_llm(mock_provider, mock_chat):
    mock_chat.return_value = {
        "summary": "早盘 LLM 摘要",
        "focus_points": ["MSS 回升"],
        "divergence_notes": [],
        "risk_alerts": [],
    }
    narrative = generate_morning_narrative(
        {"name": "澜起科技", "code": "688008", "portfolio": {"cash_ratio": 0.46}},
        {"name": "澜起科技", "verdict": "可做", "mss_final": 53.2},
        settings={"llm_narrative": {"enabled": True, "planner": "llm", "jobs": {"morning": True}}},
    )
    mock_chat.assert_called_once()
    assert narrative["planner"] == "llm"
    assert narrative["summary"] == "早盘 LLM 摘要"


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
    assert sections[-1].label == "规则解读"


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


def test_repo_config_intraday_narrative_is_deterministic():
    from pathlib import Path

    from agent_reach.daily_run.report_narrative import _narrative_cfg, narrative_use_llm
    from agent_reach.daily_run.settings import load_settings

    cfg = load_settings(path=Path("config/daily_run_settings.json"))
    narrative_cfg = _narrative_cfg(cfg, "intraday")
    assert narrative_cfg.get("planner") == "deterministic"
    assert narrative_use_llm(narrative_cfg) is False


def test_intraday_narrative_focus_includes_xueqiu_cross():
    from agent_reach.daily_run.report_narrative import generate_intraday_narrative

    scan_result = {
        "scan": {"scan_id": "S3", "name": "澜起科技", "code": "688008", "mss_final": 50, "verdict": "观察"},
        "lookback_mss": 49.0,
        "trend": "flat",
        "evaluation": {"report": {}},
        "lookback_detail": [],
        "xueqiu_cross": {
            "portfolio_hot_stocks_new": [
                {
                    "name": "澜起科技",
                    "code": "688008",
                    "role": "holding",
                    "rank": 4,
                    "board": "人气榜",
                    "percent": 0.8,
                }
            ],
            "portfolio_hot_stocks": [
                {
                    "name": "澜起科技",
                    "code": "688008",
                    "role": "holding",
                    "rank": 4,
                    "board": "人气榜",
                    "percent": 0.8,
                }
            ],
        },
    }
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_intraday_narrative(
            scan_result=scan_result,
            settings={"llm_narrative": {"enabled": True}},
        )
    joined = " ".join(narrative.get("focus_points") or [])
    assert "热股新上榜" in joined or "热股命中" in joined
    assert "澜起科技" in joined


def test_merged_intraday_narrative_deterministic():
    from agent_reach.daily_run.report_narrative import generate_merged_intraday_narrative, render_narrative_markdown

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
                "trade": {
                    "decision": {"action": "hold", "reasoning": "维持观望", "friction_blocked": True},
                    "trade": {
                        "trade_id": "T7",
                        "action": "hold",
                        "reasoning": "维持观望",
                        "friction_blocked": True,
                        "portfolio_applied": False,
                    },
                },
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
                "trade": {
                    "decision": {"action": "hold", "friction_blocked": True},
                    "trade": {
                        "trade_id": "T7",
                        "action": "hold",
                        "reasoning": "摩擦阻断",
                        "friction_blocked": True,
                        "portfolio_applied": False,
                    },
                },
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
    md = render_narrative_markdown(narrative, job="intraday")
    assert "调仓操作" in md
    assert "T7" in md
    assert "澜起科技" in md
    assert narrative.get("context_trace")


def test_intraday_narrative_includes_trade_operations():
    from agent_reach.daily_run.report_narrative import generate_intraday_narrative, render_narrative_markdown

    scan_result = {
        "scan": {"scan_id": "S7", "name": "长电科技", "code": "600584", "mss_final": 52.1, "verdict": "观察"},
        "lookback_mss": 51.8,
        "trend": "rising",
        "evaluation": {"report": {"reasoning": "MSS 回升但仍处观察区"}},
        "lookback_detail": [{"scan_id": "S7", "mss_final": 52.1, "weight": 0.5}],
    }
    trade_result = {
        "decision": {"action": "sell", "reasoning": "趋势转弱，部分止盈", "blocked": True},
        "trade": {
            "trade_id": "T7",
            "action": "sell",
            "reasoning": "趋势转弱，部分止盈",
            "blocked": True,
            "block_kind": "sell_deep_loss",
            "portfolio_applied": False,
            "portfolio_message": "深度套牢且组合覆盖不足，暂不允许卖出",
            "name": "长电科技",
            "code": "600584",
        },
    }
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_intraday_narrative(
            scan_result=scan_result,
            trade_result=trade_result,
            settings={"llm_narrative": {"enabled": True}},
        )
    md = render_narrative_markdown(narrative, job="intraday")
    assert "调仓操作" in md
    assert "T7" in md
    assert "卖出" in md
    assert "长电科技" in md
    assert "未落账" in md
    assert "MSS 52.1" in md
    assert "未落账：深度套牢" in md or "未落账：深度套牢且组合覆盖不足" in md


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


def test_close_narrative_includes_intraday_friction_whatif():
    from agent_reach.daily_run.report_narrative import _append_trade_whatif_focus

    focus: list[str] = []
    _append_trade_whatif_focus(
        focus,
        {
            "intraday_friction_whatif": {
                "skipped": False,
                "friction_would_pass": 2,
                "trend_mismatch": 1,
                "rows": [
                    {
                        "code": "000725",
                        "name": "京东方A",
                        "actual_action": "hold",
                        "evolved_action": "buy",
                    }
                ],
            }
        },
    )
    joined = " ".join(focus)
    assert "盘中摩擦/趋势对比" in joined
    assert "京东方A" in joined
    assert "可放行 2 次" in joined
    assert "趋势误判 1 次" in joined


def test_close_narrative_includes_intraday_sell_whatif():
    from agent_reach.daily_run.report_narrative import _append_trade_whatif_focus

    focus: list[str] = []
    _append_trade_whatif_focus(
        focus,
        {
            "intraday_sell_whatif": {
                "skipped": False,
                "missed_sell_signals": 2,
                "sell_share_delta": 700,
                "rows": [
                    {
                        "code": "000725",
                        "name": "京东方A",
                        "actual_action": "hold",
                        "evolved_action": "sell",
                    }
                ],
            }
        },
    )
    joined = " ".join(focus)
    assert "盘中卖出 scan replay" in joined
    assert "京东方A" in joined
    assert "错失 2 次" in joined


def test_build_baseline_evolved_verdict_down_day():
    from agent_reach.daily_run.report_narrative import build_baseline_evolved_verdict

    verdict = build_baseline_evolved_verdict(
        {
            "portfolio_daily_pnl": -8340,
            "realized_pnl": -3221,
            "sell_rules_whatif": {
                "skipped": False,
                "actual_realized_pnl": -3221,
                "hypothetical_realized_pnl": -1288,
                "realized_pnl_delta": 1932,
            },
            "buy_rules_whatif": {
                "skipped": False,
                "actual_buy_notional": 33777,
                "hypothetical_buy_notional": 0,
                "buy_notional_delta": -33777,
            },
            "intraday_sell_whatif": {
                "skipped": False,
                "sell_share_delta": -500,
                "rows": [
                    {"actual_sold": 100, "hypothetical_sold": 0},
                    {"actual_sold": 400, "hypothetical_sold": 0},
                ],
            },
            "intraday_friction_whatif": {
                "skipped": False,
                "friction_would_pass": 0,
                "trend_mismatch": 0,
                "rows": [
                    {
                        "actual_action": "sell",
                        "evolved_action": "hold",
                    }
                ],
            },
        }
    )
    assert verdict is not None
    assert verdict["overall"] == "evolved"
    assert "整体自进化更优" in verdict["summary"]
    assert "卖出少亏" in verdict["summary"]
    assert "买入少部署" in verdict["summary"]
    assert "盘中少卖 500 股" in verdict["summary"]
    assert any("卖出：" in line for line in verdict["detail_lines"])
    assert verdict.get("harness_note")


def test_render_narrative_includes_whatif_verdict():
    md = render_narrative_markdown(
        {
            "summary": "收盘全持仓 4 只复盘",
            "focus_points": ["组合当日盈亏 -8340"],
            "whatif_verdict": {
                "summary": "整体自进化更优：卖出少亏 ¥1,932，买入少部署 ¥33,777",
                "detail_lines": [
                    "卖出：基准已实现 -3,221 → 自进化 -1,288（差 +1,932，自进化更优）"
                ],
                "harness_note": "harness 买入侧会标「基准更优」",
            },
        },
        job="close",
    )
    assert "规则解读" in md
    assert "基准值 vs 自进化" in md
    assert "整体自进化更优" in md
    assert "卖出少亏" in md
    assert "harness 买入侧" in md


def test_build_harness_tuning_summary_down_day():
    from agent_reach.daily_run.report_narrative import build_harness_tuning_summary

    tuning = build_harness_tuning_summary(
        {
            "portfolio_daily_pnl": -8340,
            "sell_rules_whatif": {
                "skipped": False,
                "actual_realized_pnl": -3221,
                "hypothetical_realized_pnl": -1288,
                "realized_pnl_delta": 1932,
                "rows": [{"actual_sold": 500, "hypothetical_sold": 200, "share_delta": -300}],
            },
            "buy_rules_whatif": {
                "skipped": False,
                "actual_buy_notional": 33777,
                "hypothetical_buy_notional": 0,
                "buy_notional_delta": -33777,
                "rows": [{"actual_bought": 1500, "hypothetical_bought": 0, "share_delta": -1500}],
            },
            "intraday_friction_whatif": {
                "skipped": False,
                "friction_would_pass": 0,
                "trend_mismatch": 0,
                "rows": [],
            },
            "harness_result": {
                "layer_a": {"refinement_id": "refine_0201", "changes": 0, "job": "close"},
            },
        }
    )
    assert tuning is not None
    assert any("partial sell" in line or "sell_ratio" in line for line in tuning["policy_lines"])
    assert any("deploy_ratio" in line for line in tuning["policy_lines"])
    assert any("本次 harness" in line for line in tuning["execution_lines"])
    assert tuning.get("notes")


def test_render_narrative_includes_harness_tuning():
    md = render_narrative_markdown(
        {
            "summary": "收盘全持仓 4 只复盘",
            "focus_points": ["组合当日盈亏 -8340"],
            "harness_tuning": {
                "summary": "自进化优于基准：维持 partial sell_ratio harness 进化",
                "policy_lines": ["自进化优于基准：维持 partial sell_ratio harness 进化"],
                "plan_lines": ["weekly：维持或略收紧 sell_ratio harness，避免回归基准全卖"],
                "execution_lines": ["本次 harness 精炼 1 个 job，合计 0 项参数变更"],
            },
        },
        job="close",
    )
    assert "Harness 调参总结" in md
    assert "partial sell_ratio" in md
    assert "策略：" in md
    assert "执行：" in md


def test_build_harness_evolution_summary_weekly():
    from agent_reach.daily_run.report_narrative import build_harness_evolution_summary

    evolution = build_harness_evolution_summary(
        {
            "job": "weekly",
            "harness_result": {
                "weekly_skills": {
                    "total_changes": 152,
                    "effective_overlay": {
                        "threshold_overlay": {
                            "macro_veto": {"base": 40.0, "effective": 30.0},
                            "min_cash_ratio": {"base": 0.0, "effective": 0.5},
                        },
                        "position_overlay": {
                            "deploy_ratio": {"base": 1.0, "effective": 0.15},
                            "max_position_pct": {"base": 35.0, "effective": 15.0},
                        },
                        "trade_signals": {"defensive_trim": True, "deviation_active": True},
                    },
                    "buy_rules_whatif": {
                        "skipped": False,
                        "llm_optimal": {"deploy_ratio": 0.15, "max_position_pct": 15.0},
                    },
                },
                "layer_a": {"refinement_id": "refine_0201", "changes": 12, "job": "weekly_layer_a"},
                "layer_b": {"refinement_id": "refine_0202", "changes": 3, "job": "weekly"},
            },
        },
        settings={
            "harness_runtime": {
                "threshold_overlay": {
                    "macro_veto": {"base": 40.0, "effective": 30.0},
                    "min_cash_ratio": {"base": 0.0, "effective": 0.5},
                },
                "position_overlay": {
                    "deploy_ratio": {"base": 1.0, "effective": 0.15},
                    "max_position_pct": {"base": 35.0, "effective": 15.0},
                },
                "trade_signals": {"defensive_trim": True, "deviation_active": True},
            }
        },
    )
    assert evolution is not None
    assert evolution["total_changes"] == 152
    assert "152 项参数变更" in evolution["summary"]
    assert any("macro_veto" in line or "宏观否决线" in line for line in evolution["overlay_lines"])
    assert any("deploy_ratio" in line for line in evolution["overlay_lines"])
    assert any("DeepSeek" in line for line in evolution["signal_lines"])
    assert any("refine_0201" in line for line in evolution["execution_lines"])


def test_render_narrative_includes_harness_evolution():
    md = render_narrative_markdown(
        {
            "summary": "周报 2026-08-17~2026-08-21，净值 -103,897 元",
            "focus_points": ["本周组合 -103,897（-55.84%）"],
            "harness_evolution": {
                "summary": "本周 harness 共 152 项参数变更；宏观否决线 40→30",
                "overlay_lines": [
                    "宏观否决线 40→30",
                    "deploy_ratio 100%→15%",
                ],
                "execution_lines": ["weekly_layer_a · `refine_0201` · 12 项变更"],
            },
        },
        job="weekly",
    )
    assert "Harness 进化总结" in md
    assert "152 项参数变更" in md
    assert "宏观否决线" in md
    assert "参数：" in md
    assert "执行：" in md


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


def test_extract_close_trade_operations_uses_beijing_time():
    from agent_reach.daily_run.close_portfolio_summary import extract_close_trade_operations

    ops = extract_close_trade_operations(
        {
            "trades": [
                {
                    "at": "2026-08-21T01:01:41+00:00",
                    "actions": [
                        {
                            "side": "sell",
                            "code": "002273",
                            "name": "水晶光电",
                            "shares": 100,
                            "price": 27.13,
                            "amount": 2713.0,
                            "commission": 4.07,
                            "realized_pnl": -4.0,
                        }
                    ],
                }
            ]
        }
    )
    assert len(ops) == 1
    assert ops[0]["time"] == "2026-08-21 09:01"


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
    assert "规则解读" in footer
    assert "决策摘要" in footer
    assert footer.startswith("\n\n---\n\n")


def test_morning_context_includes_xueqiu_summary():
    ctx = build_morning_context(
        {
            "macro_signals": {
                "sentiment_posts": [{"title": "腾讯财报解读"}],
                "hot_stocks": [{"name": "澜起科技", "percent": 2.1}],
            }
        },
        {"name": "澜起科技", "verdict": "可做", "mss_final": 53.0},
    )
    assert "腾讯财报解读" in ctx["xueqiu_hot_summary"]
    assert "澜起科技" in ctx["xueqiu_hot_summary"]


def test_morning_narrative_focus_includes_xueqiu():
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_morning_narrative(
            {
                "name": "澜起科技",
                "code": "688008",
                "portfolio": {"cash_ratio": 0.46, "holdings": [{"code": "688008", "name": "澜起科技"}]},
                "macro_signals": {
                    "portfolio_hot_stocks": [
                        {
                            "code": "688008",
                            "name": "澜起科技",
                            "role": "holding",
                            "rank": 3,
                            "board": "人气榜",
                            "percent": 1.2,
                        }
                    ],
                },
            },
            {"name": "澜起科技", "verdict": "可做", "mss_final": 53.0},
            settings={"llm_narrative": {"enabled": True}},
        )
    joined = " ".join(narrative.get("focus_points") or [])
    assert "热股命中" in joined
    assert "澜起科技" in joined


def test_merged_morning_narrative_focus_includes_xueqiu():
    entries = [
        ("澜起科技", "688008", {"verdict": "可做", "mss_final": 53.0}),
        ("水晶光电", "002273", {"verdict": "观察", "mss_final": 50.0}),
    ]
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_merged_morning_narrative(
            entries,
            primary_snapshot={
                "portfolio": {
                    "cash_ratio": 0.8,
                    "holdings": [{"code": "688008", "name": "澜起科技"}],
                    "watchlist": [{"code": "603986", "name": "兆易创新"}],
                },
                "macro_signals": {
                    "portfolio_hot_stocks": [
                        {
                            "code": "688008",
                            "name": "澜起科技",
                            "role": "holding",
                            "rank": 2,
                            "board": "人气榜",
                            "percent": 1.5,
                        }
                    ],
                },
            },
            settings={"llm_narrative": {"enabled": True}},
        )
    joined = " ".join(narrative.get("focus_points") or [])
    assert "热股命中" in joined
    assert "澜起科技" in joined


@patch(
    "agent_reach.daily_run.macro_collector.fetch_xueqiu_hot_signals",
    return_value={
        "sentiment_posts": [{"title": "周六热帖", "author": "作者", "likes": 10, "url": "https://xueqiu.com/1"}],
        "hot_stocks": [{"rank": 1, "name": "澜起科技", "symbol": "SH688008", "percent": 1.5}],
        "portfolio_hot_stocks": [
            {
                "code": "688008",
                "name": "澜起科技",
                "role": "holding",
                "rank": 1,
                "board": "人气榜",
                "percent": 1.5,
            }
        ],
    },
)
def test_weekly_sections_include_xueqiu_hot(mock_fetch):
    from datetime import date

    from agent_reach.daily_run.weekly_report import generate_weekly_report

    portfolio = {
        "holdings": [{"code": "688008", "name": "澜起科技", "shares": 100, "cost": 200}],
        "watchlist": [{"code": "603986", "name": "兆易创新"}],
        "total": 75000,
        "cash": 25000,
    }
    report = generate_weekly_report(
        {"code": "688008", "portfolio": portfolio},
        {"weekly_report": {"enabled": True, "exa_sector_research": False}},
        as_of=date(2026, 7, 11),
        portfolio=portfolio,
    )
    labels = [s.label for s in render_weekly_sections(report)]
    assert "雪球热门" in labels
    hot = next(s for s in render_weekly_sections(report) if s.label == "雪球热门")
    assert "周六热帖" in hot.markdown
    assert "澜起科技" in hot.markdown
    assert "持仓/观察池 × 雪球热股" in hot.markdown
    mock_fetch.assert_called_once()


@patch(
    "agent_reach.daily_run.macro_collector.fetch_xueqiu_hot_signals",
    return_value={
        "sentiment_posts": [{"title": "周报舆情"}],
    },
)
def test_weekly_narrative_focus_includes_xueqiu(mock_fetch):
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_weekly_narrative(
            {
                "week_start": "2026-07-06",
                "week_end": "2026-07-10",
                "weekly_pnl": 1000,
                "macro_signals": {
                    "portfolio_hot_stocks": [
                        {
                            "code": "688008",
                            "name": "澜起科技",
                            "role": "holding",
                            "rank": 4,
                            "board": "人气榜",
                            "percent": 0.6,
                        }
                    ],
                },
            },
            settings={"llm_narrative": {"enabled": True}},
        )
    joined = " ".join(narrative.get("focus_points") or [])
    assert "热股命中" in joined
    assert "澜起科技" in joined


def test_close_narrative_focus_includes_xueqiu():
    from agent_reach.daily_run.report_narrative import _close_deterministic

    narrative = _close_deterministic(
        {
            "name": "澜起",
            "verify_summary": "验证通过",
            "portfolio_hot_post_summary": "热帖命中：澜起科技深度（澜起）",
        }
    )
    joined = " ".join(narrative.get("focus_points") or [])
    assert "热帖命中" in joined


def test_forecast_narrative_focus_includes_xueqiu():
    from agent_reach.daily_run.report_narrative import _forecast_deterministic

    narrative = _forecast_deterministic(
        {
            "week_start": "2026-07-28",
            "week_end": "2026-08-01",
            "symbols": [],
            "portfolio_hot_stock_summary": "热股命中：澜起科技(持仓·人气榜#3 +1.2%)",
        }
    )
    joined = " ".join(narrative.get("focus_points") or [])
    assert "热股命中" in joined


def test_morning_context_includes_watchlist_intel_and_search():
    ctx = build_morning_context(
        {
            "watchlist_intel": {
                "603986": {
                    "name": "兆易创新",
                    "announcements": [{"title": "业绩预告"}],
                }
            },
            "macro_signals": {
                "xueqiu_stock_search": [
                    {"code": "688047", "name": "龙芯中科", "query": "国产CPU"},
                ],
            },
        },
        {"name": "澜起科技", "verdict": "可做", "mss_final": 53.0},
    )
    assert "观察池情报" in ctx["watchlist_intel_summary"]
    assert "兆易创新" in ctx["watchlist_intel_summary"]
    assert ctx["xueqiu_stock_search_summary"].startswith("热点搜股：")
    assert "龙芯中科" in ctx["xueqiu_stock_search_summary"]


def test_morning_narrative_focus_includes_watchlist_intel():
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_morning_narrative(
            {
                "name": "澜起科技",
                "code": "688008",
                "portfolio": {"cash_ratio": 0.46},
                "watchlist_intel": {
                    "603986": {
                        "name": "兆易创新",
                        "announcements": [{"title": "重大合同公告"}],
                    }
                },
            },
            {"name": "澜起科技", "verdict": "可做", "mss_final": 53.0},
            settings={"llm_narrative": {"enabled": True}},
        )
    joined = " ".join(narrative.get("focus_points") or [])
    assert "观察池情报" in joined
    assert "兆易创新" in joined


def test_close_context_includes_watchlist_intel():
    ctx = build_close_context(
        snapshot={
            "name": "澜起科技",
            "macro_signals": {
                "xueqiu_stock_search": [
                    {"code": "688047", "name": "龙芯中科", "query": "国产CPU"},
                ],
            },
        },
        verify={"summary": "验证通过"},
        portfolio_summary={
            "watchlist_intel": {
                "603986": {
                    "name": "兆易创新",
                    "news": [{"title": "机构调研"}],
                }
            }
        },
    )
    assert "观察池情报" in ctx["watchlist_intel_summary"]
    assert "龙芯中科" in ctx["xueqiu_stock_search_summary"]


def test_close_narrative_focus_includes_watchlist_intel():
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_close_narrative(
            snapshot={"name": "澜起科技", "macro_signals": {}},
            verify={"summary": "验证通过"},
            portfolio_summary={
                "daily_pnl": 100,
                "watchlist_intel": {
                    "603986": {
                        "name": "兆易创新",
                        "announcements": [{"title": "业绩预告"}],
                    }
                },
            },
            settings={"llm_narrative": {"enabled": True}},
        )
    joined = " ".join(narrative.get("focus_points") or [])
    assert "观察池情报" in joined
    assert "兆易创新" in joined


def test_intraday_narrative_focus_includes_exa():
    from agent_reach.daily_run.report_narrative import _intraday_deterministic

    narrative = _intraday_deterministic(
        {
            "scan_id": "S3",
            "name": "澜起科技",
            "verdict": "观察",
            "mss_final": 52.0,
            "portfolio_hot_stocks_new_summary": "热股新上榜：兆易创新(观察池·新登关注榜#4)",
            "xueqiu_exa_summary": "Exa：兆易创新 · 新登关注榜 存储景气延续",
        }
    )
    joined = " ".join(narrative.get("focus_points") or [])
    assert "热股新上榜" in joined
    assert "Exa：" in joined


def test_weekly_context_includes_watchlist_intel_and_hit_summary():
    from agent_reach.daily_run.report_narrative import build_weekly_context

    ctx = build_weekly_context(
        {
            "week_start": "2026-07-06",
            "week_end": "2026-07-10",
            "watchlist_intel": {
                "603986": {
                    "name": "兆易创新",
                    "announcements": [{"title": "业绩预告"}],
                }
            },
        }
    )
    assert "观察池情报" in ctx["watchlist_intel_summary"]
    assert "兆易创新" in ctx["watchlist_intel_summary"]


@patch(
    "agent_reach.daily_run.report_narrative._xueqiu_hit_narrative_summary",
    return_value="雪球热榜命中率 67%（近 30 日 6 条）",
)
def test_weekly_narrative_focus_includes_intel_and_hit(mock_hit):
    from agent_reach.daily_run.report_narrative import _weekly_deterministic

    narrative = _weekly_deterministic(
        {
            "week_start": "2026-07-06",
            "week_end": "2026-07-10",
            "weekly_pnl": 1000,
            "watchlist_intel_summary": "观察池情报：兆易创新：公告：业绩预告",
            "xueqiu_hit_summary": mock_hit.return_value,
        }
    )
    joined = " ".join(narrative.get("focus_points") or [])
    assert "观察池情报" in joined
    assert "雪球热榜命中率" in joined


def test_forecast_context_includes_watchlist_intel():
    from agent_reach.daily_run.report_narrative import build_forecast_context

    ctx = build_forecast_context(
        {
            "week_start": "2026-07-28",
            "week_end": "2026-08-01",
            "watchlist_intel": {
                "688047": {
                    "name": "龙芯中科",
                    "news": [{"title": "国产CPU订单增长"}],
                }
            },
            "macro_signals": {},
        }
    )
    assert "观察池情报" in ctx["watchlist_intel_summary"]
    assert "龙芯中科" in ctx["watchlist_intel_summary"]


def test_forecast_narrative_focus_includes_watchlist_intel():
    from agent_reach.daily_run.report_narrative import _forecast_deterministic

    narrative = _forecast_deterministic(
        {
            "week_start": "2026-07-28",
            "week_end": "2026-08-01",
            "symbols": [],
            "watchlist_intel_summary": "观察池情报：龙芯中科：资讯：国产CPU订单增长",
        }
    )
    joined = " ".join(narrative.get("focus_points") or [])
    assert "观察池情报" in joined
    assert "龙芯中科" in joined

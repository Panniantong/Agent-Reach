# -*- coding: utf-8
"""Tests for OpenViking-inspired context layers."""

from pathlib import Path
from unittest.mock import patch

from agent_reach.daily_run.context_layers import (
    agentreach_uri,
    build_context_trace,
    layer0,
    layer1,
    record_harness_entry_diff,
    record_runtime_overlay_diff,
    write_text_sidecars,
    _overlay_block_diff,
)
from agent_reach.daily_run.report_narrative import (
    _attach_context_trace,
    generate_intraday_narrative,
    render_narrative_markdown,
)


def test_layer0_layer1_truncation():
    long = "中" * 300
    assert len(layer0(long)) <= 256
    assert layer1("a" * 5000).endswith("……")


def test_agentreach_uri():
    assert agentreach_uri("daily_run", "harness", "policy", "x") == (
        "agentreach://daily_run/harness/policy/x"
    )


def test_overlay_block_diff_updates():
    before = {"threshold_overlay": {"min_cash_ratio": {"base": 0.0, "effective": 0.4}}}
    after = {"threshold_overlay": {"min_cash_ratio": {"base": 0.0, "effective": 0.5}}}
    ops = _overlay_block_diff(before, after)
    assert len(ops["updates"]) == 1
    assert ops["updates"][0]["key"] == "min_cash_ratio"


def test_record_runtime_overlay_diff(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.context_layers._harness_root",
        lambda: tmp_path,
    )
    diff = record_runtime_overlay_diff(
        {},
        {"position_overlay": {"deploy_ratio": {"base": 1.0, "effective": 0.25}}},
    )
    assert diff is not None
    assert diff["summary"]["total_adds"] == 1
    assert (tmp_path / "overlay_diff.jsonl").exists()


def test_record_harness_entry_diff(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.context_layers._harness_root",
        lambda: tmp_path,
    )
    diff = record_harness_entry_diff(
        "close",
        [
            {
                "action": "update",
                "kind": "policy",
                "entry_id": "cash_guard",
                "before": {"content": "old"},
                "after": {"content": "new"},
            }
        ],
        refinement_id="refine_0001",
    )
    assert diff is not None
    assert diff["summary"]["total_updates"] == 1


def test_build_context_trace_with_overlay_and_trade():
    settings = {
        "harness_runtime": {
            "threshold_overlay": {
                "min_cash_ratio": {"base": 0.0, "effective": 0.5},
            },
            "position_overlay": {
                "deploy_ratio": {"base": 1.0, "effective": 0.25},
            },
        }
    }
    ctx = {
        "trade_action": "buy",
        "portfolio_applied": False,
        "portfolio_message": "现金不足以买入 300308 最小单位",
        "cash_limit_bypass": True,
        "consecutive_buy_streak": 3,
        "code": "300308",
    }
    intraday_trace = build_context_trace(settings, job="intraday", ctx=ctx)
    assert not any("min_cash_ratio" in line or "deploy_ratio" in line for line in intraday_trace)

    close_trace = build_context_trace(settings, job="close", ctx=ctx)
    assert any("min_cash_ratio" in line or "50%" in line for line in close_trace)
    assert any("deploy_ratio" in line or "25%" in line for line in close_trace)
    assert any("未落账" in line or "现金不足" in line for line in close_trace)


def test_build_context_trace_includes_recent_diffs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.context_layers._harness_root",
        lambda: tmp_path,
    )
    record_runtime_overlay_diff(
        {},
        {"position_overlay": {"deploy_ratio": {"base": 1.0, "effective": 0.25}}},
    )
    record_harness_entry_diff(
        "close",
        [
            {
                "action": "update",
                "kind": "policy",
                "entry_id": "cash_guard",
                "before": {"content": "old"},
                "after": {"content": "new"},
            }
        ],
    )
    trace = build_context_trace({}, ctx={})
    assert any("overlay Δ" in line and "deploy_ratio" in line for line in trace)
    assert any("harness 更新 policy/cash_guard" in line for line in trace)


def test_build_context_trace_merged_symbols_and_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.context_layers._harness_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "agent_reach.daily_run.context_store.find_cases_for_symbol",
        lambda code, limit=1: [f"{code} 历史未落账"] if code == "300308" else [],
    )
    ctx = {
        "portfolio_scope": "merged",
        "symbols": [
            {
                "code": "688008",
                "name": "澜起科技",
                "trade_action": "hold",
                "portfolio_applied": False,
                "portfolio_message": "摩擦阻断",
            },
            {
                "code": "300308",
                "name": "中际旭创",
                "trade_action": "buy",
                "portfolio_applied": False,
                "portfolio_message": "现金不足以买入 300308 最小单位",
            },
        ],
    }
    trace = build_context_trace({}, job="intraday", ctx=ctx, max_items=8)
    assert any("Case [300308]" in line for line in trace)
    assert not any("中际旭创" in line and "未落账" in line for line in trace)


def test_write_text_sidecars(tmp_path):
    target = tmp_path / "playbook.md"
    meta = write_text_sidecars(target, "第一行\n\n第二段详细内容")
    assert Path(meta["abstract"]).exists()
    assert Path(meta["overview"]).exists()
    assert "playbook.abstract.md" in meta["abstract"]


def test_narrative_renders_context_trace():
    narrative = _attach_context_trace(
        {"summary": "测试", "focus_points": ["A"], "job": "close", "planner": "deterministic"},
        settings={
            "harness_runtime": {
                "threshold_overlay": {
                    "aggressive_entry": {"base": 50, "effective": 45},
                }
            }
        },
        job="close",
    )
    md = render_narrative_markdown(narrative, job="close")
    assert "上下文轨迹" in md
    assert "aggressive_entry" in md or "45" in md


def test_intraday_narrative_includes_context_trace():
    scan_result = {
        "scan": {"scan_id": "S7", "name": "中际旭创", "code": "300308", "mss_final": 47.0, "verdict": "观察"},
        "lookback_mss": 47.0,
        "trend": "rising",
    }
    trade_result = {
        "decision": {"action": "buy", "reasoning": "条件性建仓"},
        "trade": {
            "trade_id": "T7",
            "action": "buy",
            "portfolio_applied": False,
            "portfolio_message": "现金不足以买入 300308 最小单位",
            "cash_limit_bypass": True,
            "consecutive_buy_streak": 3,
        },
    }
    with patch("agent_reach.daily_run.llm_chat.resolve_chat_provider", return_value=None):
        narrative = generate_intraday_narrative(
            scan_result=scan_result,
            trade_result=trade_result,
            settings={
                "llm_narrative": {"enabled": True},
                "harness_runtime": {
                    "position_overlay": {"deploy_ratio": {"base": 1.0, "effective": 0.25}},
                },
            },
        )
    assert narrative.get("context_trace") is not None
    md = render_narrative_markdown(narrative, job="intraday")
    assert "上下文轨迹" not in md or "阈值" not in md
    assert "调仓操作" in md
    assert "MSS 47.0" in md
    assert "突破现金/deploy 限制" in md

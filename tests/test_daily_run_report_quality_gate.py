# -*- coding: utf-8
"""Tests for report recommendation vs candidate coherence gate."""

from agent_reach.daily_run.quality_gate import validate_report
from agent_reach.daily_run.report_quality_gate import validate_report_coherence


def test_coherence_warns_on_unlisted_code_in_buy_verdict():
    report = {
        "code": "688008",
        "verdict": "可做",
        "reasoning": "关注 603986 兆易创新与 688008 澜起科技",
        "watchlist": [{"code": "688008", "name": "澜起科技"}],
    }
    warnings = validate_report_coherence(report, report, settings={"verdict_labels": {"buy": "可做"}})
    assert any("603986" in w for w in warnings)


def test_coherence_ok_when_code_in_watchlist():
    report = {
        "code": "688008",
        "verdict": "可做",
        "reasoning": "603986 与 688008 同步走强",
        "watchlist": [
            {"code": "688008", "name": "澜起科技"},
            {"code": "603986", "name": "兆易创新"},
        ],
    }
    warnings = validate_report_coherence(report, report, settings={"verdict_labels": {"buy": "可做"}})
    assert not warnings


def test_validate_report_attaches_coherence_warnings():
    report = {
        "verdict": "可做",
        "confidence": "中",
        "mss_final": 55,
        "reasoning": "建议买入 603986",
        "invalidation": "跌破 MA20",
        "evidence_chain": "- quote",
        "code": "688008",
        "entry_price": 10,
        "stop_loss_price": 9,
        "watchlist": [{"code": "688008"}],
    }
    gate = validate_report(report, {"quality_gate": {}, "verdict_labels": {"buy": "可做"}}, snapshot=report)
    assert any("603986" in w for w in gate.warnings)
    assert gate.passed is True

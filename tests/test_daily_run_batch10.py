# -*- coding: utf-8
"""Tests for Batch 10: intraday team-first, strict coherence, counter thesis."""

from unittest.mock import patch

from agent_reach.daily_run.quality_gate import validate_report, _coherence_blocks_push
from agent_reach.daily_run.team import enrich_with_team_or_experts, team_first_enabled
from agent_reach.daily_run.verdict import VerdictResult, fuse_verdict_with_team


def test_team_first_enabled_for_intraday():
    settings = {
        "team": {
            "enabled": True,
            "intraday_experts": True,
            "intraday_team_first": True,
        }
    }
    assert team_first_enabled(settings, workflow="intraday") is True


def test_enrich_with_team_or_experts_intraday_team_first():
    snapshot = {
        "code": "688008",
        "name": "澜起科技",
        "price": 100,
        "reference_price": 99,
        "ma20": 98,
        "position_20d": 0.5,
        "volume_ratio": 1.0,
        "mss_breakdown": {"fx": 40, "flow": 45, "global": 42, "sentiment": 44},
        "sources": {"quote": {"summary": "q"}, "flow": {"summary": "f"}, "sentiment": {"summary": "s"}},
        "report_type": "intraday",
    }
    settings = {
        "team": {
            "enabled": True,
            "intraday_experts": True,
            "intraday_team_first": True,
            "mode": "lite_parallel",
        },
        "thresholds": {"macro_veto": 40, "aggressive_entry": 50, "max_snapshot_age_hours": 24},
        "mss_weights": {
            "fx": 0.2,
            "flow": 0.2,
            "global": 0.15,
            "sentiment": 0.15,
            "technical": 0.15,
            "quant": 0.1,
            "risk": 0.05,
        },
    }
    enriched, steps = enrich_with_team_or_experts(snapshot, settings, workflow="intraday")
    assert steps == ["team_first"]
    assert enriched.get("team_review")
    assert enriched.get("team_mode") == "lite_parallel"
    assert len(enriched.get("expert_results") or []) == 5


@patch("agent_reach.daily_run.settings.effective_settings", side_effect=lambda settings: settings)
def test_fuse_verdict_counter_thesis_downgrade(_mock_eff):
    base = VerdictResult(
        verdict="可做",
        confidence="高",
        mss_final=58,
        entry_price=10,
        stop_loss_price=9,
        invalidation="跌破 MA20",
        reasoning="test",
        downgrade_reasons=[],
        blocked=False,
        label_key="buy",
    )
    snap = {
        "team_review": {
            "consensus_label": "可做",
            "consensus_score": 58,
            "counter_downgrade": True,
            "counter_thesis": "反面检验：风控 38 分仍偏紧",
        },
        "team_consensus_label": "可做",
    }
    settings = {
        "verdict_labels": {"buy": "可做", "watch": "观察", "avoid": "回避"},
        "team": {"counter_thesis_downgrade": True},
    }
    fused = fuse_verdict_with_team(base, snap, settings)
    assert fused.verdict == "观察"
    assert any("反面检验" in note for note in fused.downgrade_reasons)


def test_strict_coherence_blocks_morning_push():
    settings = {
        "quality_gate": {"required_fields": ["verdict", "confidence", "mss_final", "reasoning", "invalidation", "evidence_chain"]},
        "report_quality_gate": {
            "strict_coherence_enabled": True,
            "strict_workflows": ["morning", "close"],
        },
        "verdict_labels": {"buy": "可做"},
    }
    report = {
        "report_type": "premarket",
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
    gate = validate_report(report, settings, snapshot=report, workflow="morning")
    assert any("603986" in w for w in gate.warnings)
    assert gate.passed is False


def test_coherence_blocks_push_global_flag():
    settings = {"report_quality_gate": {"block_on_coherence_fail": True}}
    assert _coherence_blocks_push(["warn"], settings, workflow="intraday") is True

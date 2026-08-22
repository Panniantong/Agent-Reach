# -*- coding: utf-8
"""Tests for Batch 11: workflow unify, require_price default, trade team card, doctor."""

from agent_reach.daily_run.daily_run_diagnostics import collect_daily_run_diagnostics
from agent_reach.daily_run.intraday import TradeDecision, render_intraday_trade_markdown
from agent_reach.daily_run.plugins.pipeline import apply_pre_expert_pipeline
from agent_reach.daily_run.team import enrich_with_team_or_experts


def test_enrich_with_team_first_override():
    snapshot = {"code": "688008", "price": 100.0, "mss_breakdown": {"global": 50}}
    settings = {
        "team": {"enabled": True, "morning_experts": True, "morning_team_first": False},
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
    enriched, steps = enrich_with_team_or_experts(
        snapshot,
        settings,
        workflow="morning",
        team_first=True,
    )
    assert steps == ["team_first"]
    assert enriched.get("team_review")


def test_enrich_skip_experts():
    snapshot = {"code": "688008", "price": 1.0}
    enriched, steps = enrich_with_team_or_experts(
        snapshot,
        {"team": {"enabled": True}},
        workflow="close",
        skip_experts=True,
    )
    assert steps == []
    assert enriched == snapshot


def test_default_require_price_filter_blocks_without_price():
    out, notes = apply_pre_expert_pipeline(
        {"code": "688008", "mss_breakdown": {"global": 50}},
        {"plugins": {"pipeline_enabled": True, "transforms": ["ensure_mss_breakdown"]}},
    )
    assert out.get("expert_pipeline_blocked") == "require_price"
    assert any("require_price" in n for n in notes)


def test_render_intraday_trade_markdown_includes_team():
    decision = TradeDecision(
        action="hold",
        trade_id="T1",
        lookback_mss=52.0,
        lookback_detail=[],
        trend="flat",
        reasoning="观望",
    )
    enriched = {
        "team_review": {"consensus_score": 55, "consensus_label": "观察", "expert_results": []},
        "expert_results": [{"name": "technical", "score": 55, "summary": "中性", "success": True}],
        "team_mode": "lite_parallel",
    }
    md = render_intraday_trade_markdown(
        decision,
        [],
        {"invalidation": "跌破 MA20"},
        [{"scan_id": "S1", "mss_final": 50, "verdict": "观察"}],
        settings={"team": {"enabled": True, "intraday_experts": True}},
        enriched=enriched,
    )
    assert "Team-First" in md
    assert "前序扫描回顾" in md


def test_collect_daily_run_diagnostics():
    diag = collect_daily_run_diagnostics(
        {
            "team": {"enabled": False, "mode": "full_parallel"},
            "intent": {"enabled": True, "rate_limit_max": 30, "rate_limit_window_seconds": 300},
            "plugins": {"filters": ["require_price"]},
        }
    )
    assert "team" in diag
    assert "intent_cache" in diag
    assert "gzh_subscriptions" in diag
    assert diag["plugins"]["filters"] == ["require_price"]

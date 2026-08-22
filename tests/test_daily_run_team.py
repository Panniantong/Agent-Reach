# -*- coding: utf-8
"""Tests for Team-First 8-expert parallel runner."""

from unittest.mock import patch

from agent_reach.daily_run.settings import load_settings
from agent_reach.daily_run.team import (
    is_single_symbol_snapshot,
    render_team_markdown,
    resolve_team_experts,
    run_team_first,
    supervisor_review,
)
from agent_reach.daily_run.plugins.loader import LITE_EXPERT_NAMES


def test_run_team_first_eight_experts():
    snapshot = {
        "code": "688008",
        "name": "澜起科技",
        "price": 255.87,
        "reference_price": 255.87,
        "ma20": 260.0,
        "position_20d": 0.55,
        "volume_ratio": 1.2,
        "mss_breakdown": {"fx": 35, "flow": 48, "global": 38, "sentiment": 50},
        "sources": {
            "quote": {"summary": "q"},
            "flow": {"summary": "f"},
            "sentiment": {"summary": "s"},
        },
        "portfolio": {"cash_ratio": 0.61},
        "watchlist": [{"code": "603986", "name": "兆易创新", "change_pct": 2.5}],
    }
    enriched = run_team_first(snapshot, load_settings())
    assert len(enriched["expert_results"]) == 8
    assert enriched.get("team_review")
    assert enriched.get("team_consensus_score") is not None
    md = render_team_markdown(enriched)
    assert "Team-First" in md
    assert "基本面大师" in md
    assert "专家鉴别Agent" in md


@patch("agent_reach.daily_run.settings.effective_settings", side_effect=lambda settings: settings)
def test_supervisor_detects_conflict(_mock_eff):
    results = [
        {"name": "technical", "score": 65, "summary": "t", "success": True},
        {"name": "risk", "score": 38, "summary": "r", "success": True},
    ]
    settings = {
        "thresholds": {"macro_veto": 40, "aggressive_entry": 50, "max_snapshot_age_hours": 24},
        "mss_weights": {"fx": 0.2, "flow": 0.2, "global": 0.15, "sentiment": 0.15, "technical": 0.15, "quant": 0.1, "risk": 0.05},
    }
    review = supervisor_review({"expert_results": results}, settings)
    assert review.conflicts


def test_supervisor_counter_thesis_on_bullish():
    results = [
        {"name": "technical", "score": 65, "summary": "t", "success": True},
        {"name": "macro", "score": 62, "summary": "m", "success": True},
        {"name": "sentiment", "score": 60, "summary": "s", "success": True},
        {"name": "risk", "score": 55, "summary": "r", "success": True},
    ]
    review = supervisor_review(
        {
            "expert_results": results,
            "mss_breakdown": {"global": 35},
        },
        load_settings(),
    )
    assert review.consensus_label == "可做"
    assert review.counter_thesis.startswith("反面检验")
    md = render_team_markdown({"team_review": review.to_dict(), "expert_results": results})
    assert "反面检验" in md


def test_is_single_symbol_snapshot():
    assert is_single_symbol_snapshot({"code": "688008", "name": "澜起科技"})
    assert not is_single_symbol_snapshot({"report_type": "weekly", "code": "688008"})
    assert not is_single_symbol_snapshot(
        {"code": "688008", "portfolio": {"holdings": [{"code": "688008"}, {"code": "603986"}]}}
    )


def test_resolve_team_experts_lite_parallel():
    snapshot = {"code": "688008", "name": "澜起科技"}
    settings = {"team": {"mode": "lite_parallel", "experts": LITE_EXPERT_NAMES + ["macro"]}}
    mode, names = resolve_team_experts(snapshot, settings)
    assert mode == "lite_parallel"
    assert names == list(LITE_EXPERT_NAMES)


def test_resolve_team_experts_auto_single_symbol():
    snapshot = {"code": "688008", "name": "澜起科技"}
    settings = {"team": {"mode": "auto", "lite_on_single_symbol": True}}
    mode, names = resolve_team_experts(snapshot, settings)
    assert mode == "lite_parallel"
    assert len(names) == 5


def test_run_team_first_lite_mode():
    snapshot = {
        "code": "688008",
        "name": "澜起科技",
        "price": 255.87,
        "reference_price": 255.87,
        "ma20": 260.0,
        "position_20d": 0.55,
        "volume_ratio": 1.2,
        "mss_breakdown": {"fx": 35, "flow": 48, "global": 38, "sentiment": 50},
        "sources": {"quote": {"summary": "q"}, "flow": {"summary": "f"}, "sentiment": {"summary": "s"}},
        "portfolio": {"cash_ratio": 0.61},
    }
    settings = load_settings()
    settings = dict(settings)
    settings["team"] = dict(settings.get("team") or {})
    settings["team"]["enabled"] = True
    settings["team"]["mode"] = "lite_parallel"
    enriched = run_team_first(snapshot, settings)
    assert enriched.get("team_mode") == "lite_parallel"
    assert len(enriched["expert_results"]) == 5
    assert enriched.get("team_expert_names") == list(LITE_EXPERT_NAMES)

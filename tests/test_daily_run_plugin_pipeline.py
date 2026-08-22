# -*- coding: utf-8
"""Tests for filter/transform plugin pipeline."""

from agent_reach.daily_run.plugins.loader import list_plugins, run_experts
from agent_reach.daily_run.plugins.pipeline import apply_pre_expert_pipeline


def test_list_plugins_includes_filter_and_transform():
    kinds = {row["kind"] for row in list_plugins()}
    assert "expert" in kinds
    assert "filter" in kinds
    assert "transform" in kinds


def test_ensure_mss_breakdown_transform_fills_missing_keys():
    out, _ = apply_pre_expert_pipeline(
        {"code": "688008", "price": 100.0, "mss_breakdown": {"global": 55.0}},
        {"plugins": {"pipeline_enabled": True, "transforms": ["ensure_mss_breakdown"]}},
    )
    bd = out["mss_breakdown"]
    assert bd["global"] == 55.0
    assert "sentiment" in bd
    assert "technical" in bd


def test_require_price_filter_blocks_experts():
    out = run_experts(
        {"code": "688008", "mss_breakdown": {"global": 50}},
        {
            "plugins": {
                "pipeline_enabled": True,
                "require_price_filter_enabled": True,
                "filters": ["require_price"],
                "enabled": ["technical"],
            }
        },
    )
    assert out.get("expert_pipeline_blocked") == "require_price"
    assert "expert_results" not in out

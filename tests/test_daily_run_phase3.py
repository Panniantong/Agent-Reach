# -*- coding: utf-8
"""Phase-3 tests: plugins and optimizer."""

import json
from pathlib import Path

import pytest

from agent_reach.daily_run.optimizer import grid_search_optimize, save_optimized_settings
from agent_reach.daily_run.plugins.loader import list_plugins, run_experts
from agent_reach.daily_run.settings import load_settings


@pytest.fixture
def snapshot():
    return {
        "code": "688008",
        "name": "澜起科技",
        "price": 255.87,
        "ma20": 260.0,
        "position_20d": 0.55,
        "volume_ratio": 1.2,
        "mss_breakdown": {"fx": 35, "flow": 48, "global": 38, "sentiment": 50},
        "sources": {
            "quote": {"summary": "test"},
            "flow": {"summary": "northbound inflow"},
            "sentiment": {"summary": "positive"},
        },
    }


class TestPlugins:
    def test_list_plugins(self):
        plugins = list_plugins()
        names = {p["name"] for p in plugins}
        assert {"macro", "technical", "sentiment", "fundamental", "quant", "risk", "industry", "identifier"}.issubset(names)

    def test_run_experts_enriches_mss(self, snapshot):
        enriched = run_experts(snapshot, load_settings())
        assert "expert_scores" in enriched
        assert enriched.get("mss_final") is not None
        assert len(enriched.get("expert_results", [])) == 8

    def test_run_selected_plugins(self, snapshot):
        enriched = run_experts(snapshot, load_settings(), names=["macro"])
        assert len(enriched["expert_results"]) == 1
        assert enriched["expert_results"][0]["name"] == "macro"


class TestOptimizer:
    def test_grid_search_thresholds(self):
        history = json.loads(
            Path("config/daily_run_history.example.json").read_text(encoding="utf-8")
        )
        result = grid_search_optimize(history, load_settings(), objective="excess_return")
        assert result.best_params["macro_veto"] is not None
        assert result.best_params["aggressive_entry"] > result.best_params["macro_veto"]
        assert result.trials >= 1

    def test_grid_search_with_factors(self):
        history = json.loads(
            Path("config/daily_run_history_factors.example.json").read_text(encoding="utf-8")
        )
        result = grid_search_optimize(history, load_settings(), objective="total_return")
        assert "mss_weights" in result.best_params
        assert result.best_score is not None

    def test_save_optimized_settings(self, tmp_path, monkeypatch):
        import agent_reach.daily_run.harness as h

        monkeypatch.setattr(h, "_state_path", lambda: tmp_path / "harness_state.json")
        history = json.loads(
            Path("config/daily_run_history.example.json").read_text(encoding="utf-8")
        )
        settings = load_settings()
        settings.setdefault("harness", {})["threshold_evolution_mode"] = "fixed"
        result = grid_search_optimize(history, settings)
        out = save_optimized_settings(result, settings, path=tmp_path / "opt.json")
        saved = json.loads(out.read_text(encoding="utf-8"))
        assert saved["thresholds"]["macro_veto"] == result.best_params["macro_veto"]

# -*- coding: utf-8
"""Tests for Batch 15: Team-First defaults + StrategyOptimizer parity."""

import json
from pathlib import Path

from agent_reach.daily_run.backtest import compute_sharpe_ratio, run_mss_backtest
from agent_reach.daily_run.optimizer import grid_search_optimize, resolve_optimize_objective
from agent_reach.daily_run.settings import _DEFAULT_PATH, load_settings
from agent_reach.daily_run.strategy_optimizer import StrategyOptimizer


def test_team_enabled_by_default():
    cfg = load_settings(path=_DEFAULT_PATH)
    team = cfg.get("team") or {}
    assert team.get("enabled") is True
    assert team.get("morning_team_first") is True
    assert team.get("close_team_first") is True
    assert team.get("intraday_team_first") is True
    assert team.get("intraday_experts") is True


def test_compute_sharpe_ratio_from_equity_curve():
    curve = [100_000.0, 101_000.0, 102_000.0, 101_500.0, 103_000.0]
    sharpe = compute_sharpe_ratio(curve, periods_per_year=252)
    assert sharpe > 0


def test_run_mss_backtest_includes_sharpe():
    history = json.loads(Path("config/daily_run_history.example.json").read_text(encoding="utf-8"))
    result = run_mss_backtest(history, macro_veto=40, aggressive_entry=50)
    assert "sharpe_ratio" in result.metrics.to_dict()


def test_default_optimize_objective_is_sharpe():
    cfg = load_settings(path=_DEFAULT_PATH)
    assert resolve_optimize_objective(settings=cfg) == "sharpe"
    assert resolve_optimize_objective("excess_return", cfg) == "excess_return"


def test_strategy_optimizer_grid_search():
    history = json.loads(Path("config/daily_run_history.example.json").read_text(encoding="utf-8"))
    optimizer = StrategyOptimizer(load_settings(path=_DEFAULT_PATH))
    result = optimizer.optimize(history)
    assert result.objective == "sharpe"
    assert result.best_params["aggressive_entry"] > result.best_params["macro_veto"]
    assert "sharpe_ratio" in result.metrics


def test_strategy_optimizer_run_backtest():
    history = json.loads(Path("config/daily_run_history.example.json").read_text(encoding="utf-8"))
    optimizer = StrategyOptimizer(load_settings(path=_DEFAULT_PATH))
    bt = optimizer.run_backtest(history)
    assert bt.metrics.sharpe_ratio is not None

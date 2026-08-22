# -*- coding: utf-8
"""StrategyOptimizer parity wrapper (china-stock-analyst upstream)."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.backtest import BacktestResult, run_mss_backtest
from agent_reach.daily_run.optimizer import (
    OptimizeResult,
    grid_search_optimize,
    render_optimize_markdown,
    resolve_optimize_objective,
    save_optimized_settings,
)
from agent_reach.daily_run.settings import load_settings


class StrategyOptimizer:
    """Grid-search MSS thresholds/weights with Sharpe-first objective (upstream parity)."""

    def __init__(self, settings: Optional[dict[str, Any]] = None):
        self.settings = settings or load_settings()

    @property
    def default_objective(self) -> str:
        return resolve_optimize_objective(settings=self.settings)

    def run_backtest(
        self,
        history: list[dict[str, Any]],
        *,
        macro_veto: Optional[float] = None,
        aggressive_entry: Optional[float] = None,
    ) -> BacktestResult:
        from agent_reach.daily_run.harness_policy import aggressive_entry_default, macro_veto_default

        backtest_cfg = self.settings.get("backtest") or {}
        return run_mss_backtest(
            history,
            macro_veto=float(macro_veto if macro_veto is not None else macro_veto_default(self.settings)),
            aggressive_entry=float(
                aggressive_entry if aggressive_entry is not None else aggressive_entry_default(self.settings)
            ),
            initial_capital=float(backtest_cfg.get("default_initial_capital", 100_000)),
            commission_rate=float(backtest_cfg.get("commission_rate", 0.0015)),
        )

    def optimize(
        self,
        history: list[dict[str, Any]],
        *,
        objective: Optional[str] = None,
    ) -> OptimizeResult:
        obj = resolve_optimize_objective(objective, self.settings)
        return grid_search_optimize(history, self.settings, objective=obj)

    def save(self, result: OptimizeResult, *, path=None):
        return save_optimized_settings(result, self.settings, path=path)

    def render_markdown(self, result: OptimizeResult) -> str:
        return render_optimize_markdown(result)

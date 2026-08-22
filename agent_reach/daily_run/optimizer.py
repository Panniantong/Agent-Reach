# -*- coding: utf-8
"""Grid Search optimizer for MSS thresholds and factor weights."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from agent_reach.daily_run.backtest import BacktestResult, run_mss_backtest
from agent_reach.daily_run.settings import load_settings
from agent_reach.daily_run.verdict import compute_mss


@dataclass
class OptimizeResult:
    objective: str
    best_score: float
    best_params: dict[str, Any]
    metrics: dict[str, Any]
    trials: int
    backtest: BacktestResult

    def summary(self) -> str:
        p = self.best_params
        m = self.metrics
        return (
            f"最优 {self.objective}={self.best_score:.4f} | "
            f"veto={p.get('macro_veto')} entry={p.get('aggressive_entry')} | "
            f"收益 {m.get('total_return', 0):.2%} 超额 {m.get('excess_return', 0):.2%} "
            f"回撤 {m.get('max_drawdown', 0):.2%}"
        )


def _objective_fn(name: str) -> Callable[[BacktestResult], float]:
    objectives = {
        "excess_return": lambda r: r.metrics.excess_return,
        "total_return": lambda r: r.metrics.total_return,
        "win_rate": lambda r: r.metrics.win_rate,
        "sharpe": lambda r: r.metrics.sharpe_ratio,
        "sharpe_proxy": lambda r: (
            r.metrics.total_return / r.metrics.max_drawdown
            if r.metrics.max_drawdown > 0
            else r.metrics.total_return
        ),
    }
    if name not in objectives:
        raise ValueError(f"未知 objective: {name}，可选 {list(objectives)}")
    return objectives[name]


def resolve_optimize_objective(
    objective: Optional[str] = None,
    settings: Optional[dict[str, Any]] = None,
) -> str:
    """Resolve objective name (CLI override → settings.optimizer.default_objective)."""
    if objective:
        return str(objective)
    cfg = settings or load_settings()
    return str((cfg.get("optimizer") or {}).get("default_objective") or "sharpe")


def _history_has_factors(history: list[dict[str, Any]]) -> bool:
    keys = {"fx", "flow", "global", "sentiment"}
    return any(keys.intersection(row.keys()) for row in history)


def _apply_weights(row: dict[str, Any], weights: dict[str, float]) -> dict[str, Any]:
    out = dict(row)
    breakdown = {
        k: float(row[k])
        for k in ("fx", "flow", "global", "sentiment")
        if k in row
    }
    if breakdown:
        out["mss"] = compute_mss(breakdown, {"mss_weights": weights})
        out["mss_final"] = out["mss"]
    return out


def grid_search_optimize(
    history: list[dict[str, Any]],
    settings: Optional[dict[str, Any]] = None,
    *,
    objective: Optional[str] = None,
) -> OptimizeResult:
    """Grid search macro_veto / aggressive_entry and optionally mss_weights."""
    cfg = settings or load_settings()
    opt_cfg = cfg.get("optimizer", {})
    backtest_cfg = cfg.get("backtest", {})

    veto_grid = [float(x) for x in opt_cfg.get("macro_veto_grid", [38, 40, 42, 45])]
    entry_grid = [float(x) for x in opt_cfg.get("aggressive_entry_grid", [48, 50, 52, 55])]
    weight_grid = opt_cfg.get("mss_weight_grid") or [
        {"fx": 0.3, "flow": 0.3, "global": 0.2, "sentiment": 0.2},
        {"fx": 0.25, "flow": 0.35, "global": 0.2, "sentiment": 0.2},
        {"fx": 0.35, "flow": 0.25, "global": 0.2, "sentiment": 0.2},
    ]

    objective = resolve_optimize_objective(objective, cfg)
    score_fn = _objective_fn(objective)
    initial_capital = float(backtest_cfg.get("default_initial_capital", 100_000))
    commission = float(backtest_cfg.get("commission_rate", 0.0015))

    best: Optional[OptimizeResult] = None
    trials = 0
    use_weights = _history_has_factors(history)

    weight_candidates = weight_grid if use_weights else [cfg.get("mss_weights", {})]

    for weights in weight_candidates:
        weighted_history = [_apply_weights(row, weights) for row in history]
        for veto in veto_grid:
            for entry in entry_grid:
                if entry <= veto:
                    continue
                trials += 1
                bt = run_mss_backtest(
                    weighted_history,
                    macro_veto=veto,
                    aggressive_entry=entry,
                    initial_capital=initial_capital,
                    commission_rate=commission,
                )
                score = score_fn(bt)
                params = {
                    "macro_veto": veto,
                    "aggressive_entry": entry,
                    "mss_weights": weights if use_weights else cfg.get("mss_weights"),
                }
                if best is None or score > best.best_score:
                    best = OptimizeResult(
                        objective=objective,
                        best_score=score,
                        best_params=params,
                        metrics=bt.metrics.to_dict(),
                        trials=trials,
                        backtest=bt,
                    )

    if best is None:
        raise ValueError("优化未产生有效结果，请检查 history 与 grid 配置")

    best.trials = trials
    return best


def save_optimized_settings(
    result: OptimizeResult,
    settings: Optional[dict[str, Any]] = None,
    *,
    path: Optional[Path] = None,
) -> Path:
    """Persist optimizer run metadata; thresholds go to harness when evolution mode is harness."""
    from agent_reach.daily_run.harness_policy import harness_evolution_mode

    base = settings or load_settings()
    cfg = copy.deepcopy(base)
    params = result.best_params
    harness_mode = harness_evolution_mode(cfg) == "harness"

    if harness_mode:
        from agent_reach.daily_run.optimizer_harness import apply_optimizer_harness_refinement

        apply_optimizer_harness_refinement(result, settings=cfg)
    else:
        cfg.setdefault("thresholds", {})
        cfg["thresholds"]["macro_veto"] = params["macro_veto"]
        cfg["thresholds"]["aggressive_entry"] = params["aggressive_entry"]
        cfg.setdefault("backtest", {})
        cfg["backtest"]["macro_veto"] = params["macro_veto"]
        cfg["backtest"]["aggressive_entry"] = params["aggressive_entry"]

    if params.get("mss_weights"):
        cfg["mss_weights"] = params["mss_weights"]

    cfg["optimizer"] = cfg.get("optimizer", {})
    cfg["optimizer"]["last_run"] = {
        "objective": result.objective,
        "best_score": result.best_score,
        "best_params": params,
        "metrics": result.metrics,
        "harness_mode": harness_mode,
    }

    out = path or (Path.home() / ".agent-reach" / "daily_run_settings.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def render_optimize_markdown(result: OptimizeResult) -> str:
    p = result.best_params
    m = result.metrics
    lines = [
        f"**优化摘要：** {result.summary()}",
        "",
        "| 参数 | 最优值 |",
        "|------|--------|",
        f"| macro_veto | {p.get('macro_veto')} |",
        f"| aggressive_entry | {p.get('aggressive_entry')} |",
        f"| 试验次数 | {result.trials} |",
        "",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| 策略收益 | {m.get('total_return', 0):.2%} |",
        f"| 超额收益 | {m.get('excess_return', 0):.2%} |",
        f"| 最大回撤 | {m.get('max_drawdown', 0):.2%} |",
        f"| 胜率 | {m.get('win_rate', 0):.1%} |",
        f"| Sharpe | {m.get('sharpe_ratio', 0):.2f} |",
    ]
    weights = p.get("mss_weights")
    if isinstance(weights, dict) and weights:
        lines.extend(["", "**MSS 权重：**", json.dumps(weights, ensure_ascii=False)])
    return "\n".join(lines)

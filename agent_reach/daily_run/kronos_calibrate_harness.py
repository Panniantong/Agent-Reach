# -*- coding: utf-8
"""Weekly Kronos hold-out grid → harness inference policy lines."""

from __future__ import annotations

import itertools
from copy import deepcopy
from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement, merge_harness_evidence
from agent_reach.daily_run.kronos_calibration import (
    load_kronos_error_ledger,
    summarize_kronos_ledger,
)
from agent_reach.daily_run.kronos_inference_policy import (
    _KRONOS_INFERENCE_BOUNDS,
    _KRONOS_INFERENCE_NEUTRAL,
    format_kronos_inference_policy_line,
    format_kronos_symbol_blend_policy_line,
    kronos_inference_policy_base,
)
from agent_reach.daily_run.kronos_predictor import is_kronos_enabled, kronos_cfg


def kronos_calibrate_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    block = dict(kronos_cfg(settings).get("calibrate") or {})
    grid = dict(block.get("grid") or {})
    return {
        "enabled": block.get("enabled", True) is not False,
        "lookback_days": max(7, int(block.get("lookback_days", 14))),
        "max_codes": max(1, int(block.get("max_codes", 6))),
        "holdout_days": max(1, int(block.get("holdout_days", 5))),
        "holdout_folds": max(1, int(block.get("holdout_folds", 1))),
        "grid": {
            "inference_T": list(grid.get("inference_T") or [0.4, 0.6, 0.8]),
            "inference_sample_count": list(grid.get("inference_sample_count") or [3, 5]),
            "week_forecast_blend_weight": list(
                grid.get("week_forecast_blend_weight") or [0.25, 0.35, 0.45]
            ),
        },
    }


def _grid_values(name: str, cfg: dict[str, Any]) -> list[float]:
    raw = cfg["grid"].get(name) or []
    lo, hi = _KRONOS_INFERENCE_BOUNDS[name]
    out: list[float] = []
    for val in raw:
        out.append(round(max(lo, min(hi, float(val))), 3))
    return out or [float(_KRONOS_INFERENCE_NEUTRAL[name])]


def _score_holdout(result: dict[str, Any]) -> float:
    summary = result.get("summary") or {}
    dir_rate = float(summary.get("direction_hit_rate") or 0)
    mae = float(summary.get("mean_abs_close_error_pct") or 99)
    chg_err = abs(float(summary.get("mean_change_error_pct") or 0))
    # Higher direction hit, lower MAE/change error
    return round((1.0 - dir_rate) * 10.0 + mae * 0.5 + chg_err * 0.3, 6)


def _collect_codes(report: dict[str, Any], *, settings: dict[str, Any], max_codes: int) -> list[str]:
    from agent_reach.daily_run.snapshot_builder import _normalize_code

    codes: list[str] = []
    pf = report.get("portfolio") or {}
    for bucket in ("holdings", "watchlist"):
        for row in pf.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            code = _normalize_code(str(row.get("code") or ""))
            if code and code not in codes:
                codes.append(code)
    ledger = summarize_kronos_ledger(
        load_kronos_error_ledger(limit=500),
        lookback_days=kronos_calibrate_cfg(settings)["lookback_days"],
    )
    for code in ledger.get("divergence_heavy_codes") or []:
        norm = _normalize_code(str(code))
        if norm and norm not in codes:
            codes.append(norm)
    return codes[:max_codes]


def run_kronos_inference_grid(
    codes: list[str],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Grid-search Kronos inference hyperparams via AKShare hold-out backtest."""
    from agent_reach.daily_run.kronos_holdout_backtest import run_kronos_holdout_backtest

    cfg = kronos_calibrate_cfg(settings)
    if not codes:
        return {"skipped": True, "reason": "no codes for kronos grid", "job": "kronos_calibrate"}

    grid_keys = ("inference_T", "inference_sample_count", "week_forecast_blend_weight")
    combos = list(
        itertools.product(*(_grid_values(k, cfg) for k in grid_keys))
    )
    base = kronos_inference_policy_base(settings)
    best: Optional[dict[str, Any]] = None
    trials: list[dict[str, Any]] = []

    for combo in combos:
        params = dict(zip(grid_keys, combo))
        params["inference_top_p"] = float(base.get("inference_top_p", 0.9))
        trial_scores: list[float] = []
        code_results: dict[str, Any] = {}
        for code in codes:
            trial_settings = deepcopy(settings or {})
            trial_settings["kronos"] = {**kronos_cfg(settings), **params}
            result = run_kronos_holdout_backtest(
                code,
                holdout_days=cfg["holdout_days"],
                folds=cfg["holdout_folds"],
                settings=trial_settings,
            )
            code_results[code] = result
            if result.get("available"):
                trial_scores.append(_score_holdout(result))
        if not trial_scores:
            continue
        loss = sum(trial_scores) / len(trial_scores)
        row = {"params": params, "loss": round(loss, 6), "codes": len(trial_scores)}
        trials.append(row)
        if best is None or loss < float(best["loss"]):
            best = {**row, "code_results": code_results}

    if not best:
        return {
            "skipped": True,
            "reason": "hold-out grid produced no scores (Kronos/AKShare unavailable?)",
            "job": "kronos_calibrate",
            "codes": codes,
            "trials": len(combos),
        }

    return {
        "skipped": False,
        "planner": "grid",
        "codes": codes,
        "trials_run": len(trials),
        "trials_requested": len(combos),
        "best": best,
        "ledger_summary": summarize_kronos_ledger(
            load_kronos_error_ledger(limit=500),
            lookback_days=cfg["lookback_days"],
        ),
    }


def kronos_calibrate_to_harness_evidence(result: dict[str, Any]) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []

    if result.get("skipped"):
        return {
            "memory": memory,
            "policy": policy,
            "playbook": playbook,
            "plan": [],
            "summary": f"kronos_calibrate skipped: {result.get('reason')}",
        }

    best = result.get("best") or {}
    params = dict(best.get("params") or {})
    if not params:
        return {
            "memory": memory,
            "policy": policy,
            "playbook": playbook,
            "plan": [],
            "summary": "kronos_calibrate no params",
        }

    loss = best.get("loss")
    memory.append(
        f"Kronos hold-out grid {result.get('trials_run')}/{result.get('trials_requested')} "
        f"codes={len(result.get('codes') or [])} loss={loss}"
    )
    policy_line = format_kronos_inference_policy_line(
        params,
        rationale=f"hold-out grid loss={loss}",
    )
    if policy_line:
        policy.append(policy_line)

    ledger = result.get("ledger_summary") or {}
    heavy = ledger.get("divergence_heavy_codes") or []
    base_blend = float(params.get("week_forecast_blend_weight") or 0.35)
    if heavy:
        blends = {code: round(max(0.2, base_blend - 0.1), 3) for code in heavy[:5]}
        blend_line = format_kronos_symbol_blend_policy_line(
            blends,
            rationale="ledger divergence-heavy",
        )
        if blend_line:
            policy.append(blend_line)
            memory.append(f"Kronos 分歧重标 blend 下调 {len(blends)} 只")

    playbook.append(
        "Kronos 增训 L1：error_ledger → hold-out grid → harness inference policy（非权重 finetune）"
    )

    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": [],
        "summary": f"kronos_calibrate loss={loss}",
    }


def apply_kronos_calibrate_harness_refinement(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg_block = kronos_calibrate_cfg(settings)
    if not cfg_block["enabled"]:
        return {"skipped": True, "reason": "kronos.calibrate.enabled=false", "job": "kronos_calibrate"}
    if not is_kronos_enabled(settings):
        return {"skipped": True, "reason": "kronos disabled", "job": "kronos_calibrate"}
    k_cfg = kronos_cfg(settings)
    if k_cfg.get("harness_evolve", True) is False:
        return {"skipped": True, "reason": "kronos.harness_evolve disabled", "job": "kronos_calibrate"}

    codes = _collect_codes(report, settings=settings or {}, max_codes=cfg_block["max_codes"])
    result = run_kronos_inference_grid(codes, settings=settings)
    evidence = kronos_calibrate_to_harness_evidence(result)
    refine = apply_skill_refinement("kronos_calibrate", evidence, settings=settings)
    return {**result, **refine}

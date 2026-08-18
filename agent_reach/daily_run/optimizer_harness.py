# -*- coding: utf-8
"""Grid-search optimizer results → harness self-evolution (no static JSON threshold writeback)."""

from __future__ import annotations

import json
from typing import Any, Optional, TYPE_CHECKING

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement

if TYPE_CHECKING:
    from agent_reach.daily_run.optimizer import OptimizeResult


def optimize_to_harness_evidence(result: "OptimizeResult") -> dict[str, Any]:
    params = result.best_params
    metrics = result.metrics
    veto = params.get("macro_veto")
    entry = params.get("aggressive_entry")
    memory = [
        result.summary(),
        (
            f"回测试验 {result.trials} 组 | {result.objective}={result.best_score:.4f} | "
            f"收益 {float(metrics.get('total_return', 0)):.2%} "
            f"超额 {float(metrics.get('excess_return', 0)):.2%} "
            f"回撤 {float(metrics.get('max_drawdown', 0)):.2%}"
        ),
    ]
    policy: list[str] = []
    if veto is not None and entry is not None:
        policy.append(
            f"optimizer grid: macro_veto={float(veto):g} aggressive_entry={float(entry):g} "
            f"objective={result.objective} score={result.best_score:.4f}"
        )
    playbook = [
        f"回测优化阈值 macro_veto={veto} aggressive_entry={entry}（{result.objective}={result.best_score:.4f}）",
    ]
    weights = params.get("mss_weights")
    if isinstance(weights, dict) and weights:
        playbook.append(f"MSS 权重优化：{json.dumps(weights, ensure_ascii=False)}")
    plan: list[str] = []
    if veto is not None and entry is not None:
        plan.append(f"verify 下一交易日 MSS 与 macro_veto={float(veto):g} / entry={float(entry):g} 对齐度")
    summary = f"optimize {result.objective}={result.best_score:.4f} veto={veto} entry={entry}"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def apply_optimizer_harness_refinement(
    result: "OptimizeResult",
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    evidence = optimize_to_harness_evidence(result)
    evidence["forge_domain"] = {
        "best_params": result.best_params,
        "best_score": result.best_score,
        "trials": result.trials,
        "metrics": result.metrics,
    }
    evidence["rigor_domain"] = dict(evidence["forge_domain"])
    return apply_skill_refinement("optimize", evidence, settings=settings, enabled_flag="optimizer")

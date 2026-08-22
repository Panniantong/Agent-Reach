# -*- coding: utf-8
"""Discover and run daily-run expert plugins."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from agent_reach.daily_run.plugins.base import ExpertPlugin, PluginContext, PluginResult
from agent_reach.daily_run.plugins.fundamental_expert import FundamentalExpert
from agent_reach.daily_run.plugins.industry_expert import IndustryExpert
from agent_reach.daily_run.plugins.identifier_expert import IdentifierExpert
from agent_reach.daily_run.plugins.macro_expert import MacroExpert
from agent_reach.daily_run.plugins.quant_expert import QuantExpert
from agent_reach.daily_run.plugins.risk_expert import RiskExpert
from agent_reach.daily_run.plugins.sentiment_expert import SentimentExpert
from agent_reach.daily_run.plugins.technical_expert import TechnicalExpert
from agent_reach.daily_run.settings import effective_settings, load_settings
from agent_reach.daily_run.verdict import compute_mss

TEAM_EXPERT_NAMES: list[str] = [
    "fundamental",
    "technical",
    "quant",
    "risk",
    "macro",
    "industry",
    "sentiment",
    "identifier",
]

LITE_EXPERT_NAMES: list[str] = [
    "fundamental",
    "technical",
    "quant",
    "risk",
    "identifier",
]

MSS_EXPERT_NAMES: list[str] = [
    "technical",
    "quant",
    "risk",
    "fundamental",
]

_BUILTIN: list[ExpertPlugin] = [
    FundamentalExpert(),
    TechnicalExpert(),
    QuantExpert(),
    RiskExpert(),
    MacroExpert(),
    IndustryExpert(),
    SentimentExpert(),
    IdentifierExpert(),
]

_BY_NAME: dict[str, ExpertPlugin] = {p.name: p for p in _BUILTIN}


def list_plugins() -> list[dict[str, str]]:
    from agent_reach.daily_run.plugins.pipeline import list_filter_plugins, list_transform_plugins

    rows = [{"name": p.name, "description": p.description, "kind": "expert"} for p in _BUILTIN]
    rows.extend({**row, "kind": "filter"} for row in list_filter_plugins())
    rows.extend({**row, "kind": "transform"} for row in list_transform_plugins())
    return rows


def get_plugin(name: str) -> ExpertPlugin | None:
    return _BY_NAME.get(name)


def _run_plugin(plugin: ExpertPlugin, ctx: PluginContext) -> PluginResult:
    try:
        return plugin.run(ctx)
    except Exception as exc:
        return PluginResult(
            name=plugin.name,
            score=50.0,
            summary=f"专家异常降级：{exc}",
            success=False,
            details={"error": str(exc)},
        )


def _run_parallel(selected: list[ExpertPlugin], ctx: PluginContext) -> list[PluginResult]:
    results: list[PluginResult] = []
    with ThreadPoolExecutor(max_workers=min(len(selected), 8)) as pool:
        futures = {pool.submit(_run_plugin, p, ctx): p for p in selected}
        for future in as_completed(futures):
            results.append(future.result())
    order = {p.name: i for i, p in enumerate(selected)}
    results.sort(key=lambda r: order.get(r.name, 99))
    return results


def run_experts(
    snapshot: dict[str, Any],
    settings: dict[str, Any] | None = None,
    *,
    names: list[str] | None = None,
    parallel: bool | None = None,
) -> dict[str, Any]:
    """Run expert plugins (parallel by default) and merge scores into snapshot."""
    cfg = effective_settings(settings or load_settings())
    plugin_cfg = cfg.get("plugins", {})
    use_parallel = parallel if parallel is not None else plugin_cfg.get("parallel", True)

    from agent_reach.daily_run.plugins.pipeline import apply_pre_expert_pipeline

    prepared, pipeline_notes = apply_pre_expert_pipeline(snapshot, cfg)
    if prepared.get("expert_pipeline_blocked"):
        blocked = dict(prepared)
        blocked["expert_pipeline_notes"] = pipeline_notes
        return blocked

    enabled = names or plugin_cfg.get("enabled") or TEAM_EXPERT_NAMES
    selected = [_BY_NAME[n] for n in enabled if n in _BY_NAME]
    if names and not selected:
        raise ValueError(f"未知插件：{names}")

    ctx = PluginContext(snapshot=prepared, settings=cfg)

    if use_parallel and len(selected) > 1:
        results = _run_parallel(selected, ctx)
    else:
        results = [_run_plugin(p, ctx) for p in selected]

    expert_scores: dict[str, float] = {r.name: r.score for r in results}

    merged = dict(prepared)
    if pipeline_notes:
        merged["expert_pipeline_notes"] = pipeline_notes
    merged["expert_scores"] = expert_scores
    merged["expert_results"] = [r.to_dict() for r in results]

    breakdown = dict(merged.get("mss_breakdown") or {})
    if "global" not in breakdown and "macro" in expert_scores:
        breakdown.setdefault("fx", expert_scores["macro"])
        breakdown.setdefault("global", expert_scores["macro"])
    if "flow" not in breakdown and "sentiment" in expert_scores:
        breakdown.setdefault("flow", expert_scores["sentiment"])
        breakdown.setdefault("sentiment", expert_scores["sentiment"])
    if expert_scores.get("technical") is not None:
        breakdown["technical"] = expert_scores["technical"]
    if expert_scores.get("quant") is not None:
        breakdown["quant"] = expert_scores["quant"]
    if expert_scores.get("risk") is not None:
        breakdown["risk"] = expert_scores["risk"]

    merged["mss_breakdown"] = breakdown
    merged["mss_final"] = compute_mss(breakdown, cfg)
    return merged

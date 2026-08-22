# -*- coding: utf-8
"""Built-in filter/transform plugins and pre-expert pipeline."""

from __future__ import annotations

from typing import Any

from agent_reach.daily_run.plugins.base import FilterPlugin, PluginContext, TransformPlugin


class RequirePriceFilter(FilterPlugin):
    name = "require_price"
    description = "Skip experts when snapshot lacks price/reference_price"

    def apply(self, context: PluginContext) -> bool:
        plugins = context.settings.get("plugins") or {}
        if plugins.get("require_price_filter_enabled") is False:
            return True
        snap = context.snapshot
        price = snap.get("price") or snap.get("reference_price")
        return price is not None and float(price) > 0


class EnsureMssBreakdownTransform(TransformPlugin):
    name = "ensure_mss_breakdown"
    description = "Fill missing MSS breakdown keys with macro baseline"

    def transform(self, snapshot: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        from agent_reach.daily_run.harness_policy import macro_factor_baseline_default

        out = dict(snapshot)
        breakdown = dict(out.get("mss_breakdown") or {})
        baseline = macro_factor_baseline_default(settings)
        for key in ("fx", "flow", "global", "sentiment", "technical", "quant", "risk"):
            if key not in breakdown:
                breakdown[key] = float(baseline if key in ("fx", "flow", "global", "sentiment") else 50.0)
        out["mss_breakdown"] = breakdown
        return out


_BUILTIN_FILTERS: list[FilterPlugin] = [RequirePriceFilter()]
_BUILTIN_TRANSFORMS: list[TransformPlugin] = [EnsureMssBreakdownTransform()]

_FILTERS_BY_NAME = {p.name: p for p in _BUILTIN_FILTERS}
_TRANSFORMS_BY_NAME = {p.name: p for p in _BUILTIN_TRANSFORMS}


def list_filter_plugins() -> list[dict[str, str]]:
    return [{"name": p.name, "description": p.description} for p in _BUILTIN_FILTERS]


def list_transform_plugins() -> list[dict[str, str]]:
    return [{"name": p.name, "description": p.description} for p in _BUILTIN_TRANSFORMS]


def _enabled_names(
    cfg: dict[str, Any],
    key: str,
    defaults: list[str],
    registry: dict[str, Any],
) -> list[str]:
    raw = cfg.get(key)
    names = list(defaults) if raw is None else [str(n) for n in raw]
    return [n for n in names if n in registry]


def apply_pre_expert_pipeline(
    snapshot: dict[str, Any],
    settings: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Run filter + transform plugins before expert execution."""
    plugins = settings.get("plugins") or {}
    if plugins.get("pipeline_enabled") is False:
        return dict(snapshot), []

    ctx = PluginContext(snapshot=snapshot, settings=settings)
    notes: list[str] = []

    filter_names = _enabled_names(
        plugins,
        "filters",
        ["require_price"],
        _FILTERS_BY_NAME,
    )
    if plugins.get("require_price_filter_enabled") is False:
        filter_names = [n for n in filter_names if n != "require_price"]
    for name in filter_names:
        plugin = _FILTERS_BY_NAME.get(name)
        if not plugin:
            continue
        if not plugin.apply(ctx):
            notes.append(f"filter:{name}:blocked")
            out = dict(snapshot)
            out["expert_pipeline_blocked"] = name
            return out, notes

    out = dict(snapshot)
    transform_names = _enabled_names(
        plugins,
        "transforms",
        ["ensure_mss_breakdown"],
        _TRANSFORMS_BY_NAME,
    )
    for name in transform_names:
        plugin = _TRANSFORMS_BY_NAME.get(name)
        if plugin:
            out = plugin.transform(out, settings)
    return out, notes

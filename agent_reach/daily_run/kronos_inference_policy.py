# -*- coding: utf-8
"""Harness-evolved Kronos inference hyperparameters (Layer 1, not weight finetune)."""

from __future__ import annotations

import re
from typing import Any, Optional

_KRONOS_INFERENCE_PREFIX = "Kronos inference最优"
_KRONOS_INFERENCE_RE = re.compile(
    r"Kronos inference最优[：:]\s*"
    r"inference_T=([\d.]+)\s+"
    r"inference_top_p=([\d.]+)\s+"
    r"inference_sample_count=([\d.]+)\s+"
    r"week_forecast_blend_weight=([\d.]+)",
    re.IGNORECASE,
)

_KRONOS_INFERENCE_FLOAT_KEYS: tuple[str, ...] = (
    "inference_T",
    "inference_top_p",
    "week_forecast_blend_weight",
)
_KRONOS_INFERENCE_INT_KEYS: tuple[str, ...] = ("inference_sample_count",)
_KRONOS_INFERENCE_KEYS: tuple[str, ...] = (
    "inference_T",
    "inference_top_p",
    "inference_sample_count",
    "week_forecast_blend_weight",
)

_KRONOS_INFERENCE_BOUNDS: dict[str, tuple[float, float]] = {
    "inference_T": (0.4, 1.0),
    "inference_top_p": (0.85, 0.95),
    "inference_sample_count": (3.0, 5.0),
    "week_forecast_blend_weight": (0.2, 0.5),
}

_KRONOS_INFERENCE_NEUTRAL: dict[str, float] = {
    "inference_T": 0.6,
    "inference_top_p": 0.9,
    "inference_sample_count": 5.0,
    "week_forecast_blend_weight": 0.35,
}

_KRONOS_SYMBOL_BLEND_PREFIX = "Kronos symbol_blend"
_KRONOS_SYMBOL_BLEND_RE = re.compile(
    r"Kronos symbol_blend[：:]\s*(.+?)(?:\s*[—\-]\s*|$)",
    re.IGNORECASE,
)
_KRONOS_SYMBOL_PAIR_RE = re.compile(r"(\d{6})=([\d.]+)")


def _kronos_section(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("kronos") or {})


def kronos_inference_mode(settings: Optional[dict[str, Any]] = None) -> str:
    sec = _kronos_section(settings)
    mode = str(sec.get("inference_mode") or sec.get("mode") or "harness").strip().lower()
    return mode if mode in {"harness", "fixed"} else "harness"


def kronos_inference_policy_base(settings: Optional[dict[str, Any]] = None) -> dict[str, float]:
    sec = _kronos_section(settings)
    merged = dict(_KRONOS_INFERENCE_NEUTRAL)
    for key in _KRONOS_INFERENCE_KEYS:
        if key in sec:
            merged[key] = float(sec[key])
    return merged


def _clamp_inference_policy(raw: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in _KRONOS_INFERENCE_KEYS:
        val = raw.get(key)
        if val is None:
            continue
        lo, hi = _KRONOS_INFERENCE_BOUNDS[key]
        out[key] = round(max(lo, min(hi, float(val))), 3)
    return out


def _format_inference_value(key: str, value: float) -> str:
    if key in _KRONOS_INFERENCE_INT_KEYS:
        return str(int(round(float(value))))
    text = f"{float(value):.4f}".rstrip("0").rstrip(".")
    return text or "0"


def format_kronos_inference_policy_line(ratios: dict[str, float], *, rationale: str = "") -> str:
    parts = [
        f"{key}={_format_inference_value(key, ratios[key])}"
        for key in _KRONOS_INFERENCE_KEYS
        if key in ratios
    ]
    if len(parts) < len(_KRONOS_INFERENCE_KEYS):
        return ""
    line = f"{_KRONOS_INFERENCE_PREFIX}：" + " ".join(parts)
    reason = str(rationale or "").strip()
    if reason:
        line += f" — {reason[:120]}"
    return line


def parse_kronos_inference_policy_line(text: str) -> Optional[dict[str, float]]:
    match = _KRONOS_INFERENCE_RE.search(str(text or ""))
    if not match:
        return None
    raw = {key: float(match.group(i + 1)) for i, key in enumerate(_KRONOS_INFERENCE_KEYS)}
    return _clamp_inference_policy(raw)


def format_kronos_symbol_blend_policy_line(
    blends: dict[str, float],
    *,
    rationale: str = "",
) -> str:
    if not blends:
        return ""
    parts = [
        f"{code}={_format_inference_value('week_forecast_blend_weight', val)}"
        for code, val in sorted(blends.items())
    ]
    line = f"{_KRONOS_SYMBOL_BLEND_PREFIX}：" + " ".join(parts)
    reason = str(rationale or "").strip()
    if reason:
        line += f" — {reason[:120]}"
    return line


def parse_kronos_symbol_blend_policy_line(text: str) -> dict[str, float]:
    match = _KRONOS_SYMBOL_BLEND_RE.search(str(text or ""))
    if not match:
        return {}
    blob = match.group(1)
    out: dict[str, float] = {}
    for code, val in _KRONOS_SYMBOL_PAIR_RE.findall(blob):
        lo, hi = _KRONOS_INFERENCE_BOUNDS["week_forecast_blend_weight"]
        out[code] = round(max(lo, min(hi, float(val))), 3)
    return out


def _find_inference_in_state(state: Any, *, settings: dict[str, Any]) -> Optional[dict[str, float]]:
    from agent_reach.daily_run.harness_policy import _collect_text_blobs, _overlay_sources

    for blob in _collect_text_blobs(
        state, sources=_overlay_sources(settings), kind="policy", settings=settings
    ):
        parsed = parse_kronos_inference_policy_line(blob)
        if parsed:
            return parsed
    return None


def _find_symbol_blend_in_state(state: Any, *, settings: dict[str, Any]) -> dict[str, float]:
    from agent_reach.daily_run.harness_policy import _collect_text_blobs, _overlay_sources

    merged: dict[str, float] = {}
    for blob in _collect_text_blobs(
        state, sources=_overlay_sources(settings), kind="policy", settings=settings
    ):
        parsed = parse_kronos_symbol_blend_policy_line(blob)
        if parsed:
            merged.update(parsed)
    return merged


def resolve_harness_kronos_inference_policy(
    state: Any,
    *,
    settings: dict[str, Any],
) -> dict[str, float]:
    merged = kronos_inference_policy_base(settings)
    if kronos_inference_mode(settings) != "harness":
        return _clamp_inference_policy(merged)
    from agent_reach.daily_run.harness_policy import _overlay_enabled

    if not _overlay_enabled(settings):
        return _clamp_inference_policy(merged)
    optimal = _find_inference_in_state(state, settings=settings)
    if optimal:
        merged.update(optimal)
    return _clamp_inference_policy(merged)


def resolve_harness_kronos_symbol_blend(
    state: Any,
    *,
    settings: dict[str, Any],
) -> dict[str, float]:
    if kronos_inference_mode(settings) != "harness":
        return {}
    from agent_reach.daily_run.harness_policy import _overlay_enabled

    if not _overlay_enabled(settings):
        return {}
    return _find_symbol_blend_in_state(state, settings=settings)


def _kronos_inference_policy(settings: Optional[dict[str, Any]] = None) -> dict[str, float]:
    cfg = settings or {}
    if kronos_inference_mode(cfg) == "fixed":
        return _clamp_inference_policy(kronos_inference_policy_base(cfg))
    runtime = cfg.get("harness_runtime") or {}
    cached = runtime.get("kronos_inference_policy")
    if isinstance(cached, dict) and cached:
        merged = kronos_inference_policy_base(cfg)
        merged.update({k: float(v) for k, v in cached.items() if k in _KRONOS_INFERENCE_KEYS})
        return _clamp_inference_policy(merged)
    from agent_reach.daily_run.harness_policy import _overlay_enabled

    if not _overlay_enabled(cfg):
        return _clamp_inference_policy(kronos_inference_policy_base(cfg))
    from agent_reach.daily_run.harness import load_harness

    return resolve_harness_kronos_inference_policy(load_harness(), settings=cfg)


def _kronos_symbol_blend(settings: Optional[dict[str, Any]] = None) -> dict[str, float]:
    cfg = settings or {}
    runtime = cfg.get("harness_runtime") or {}
    cached = runtime.get("kronos_symbol_blend")
    if isinstance(cached, dict):
        return {str(k): float(v) for k, v in cached.items()}
    from agent_reach.daily_run.harness_policy import _overlay_enabled

    if not _overlay_enabled(cfg):
        return {}
    from agent_reach.daily_run.harness import load_harness

    return resolve_harness_kronos_symbol_blend(load_harness(), settings=cfg)


def resolve_symbol_blend_weight(code: str, settings: Optional[dict[str, Any]] = None) -> float:
    """Effective MC/Kronos blend weight for one symbol (global or per-symbol overlay)."""
    sym = str(code or "").strip()
    per_symbol = _kronos_symbol_blend(settings)
    if sym in per_symbol:
        return float(per_symbol[sym])
    return float(_kronos_inference_policy(settings).get("week_forecast_blend_weight", 0.35))


def kronos_effective_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Merge harness-evolved inference params into kronos settings block."""
    sec = dict(_kronos_section(settings))
    policy = _kronos_inference_policy(settings)
    sec.update({k: policy[k] for k in policy})
    return sec


def harness_kronos_inference_overlay_meta(
    base: dict[str, float],
    effective: dict[str, float],
) -> dict[str, Any]:
    changed: dict[str, dict[str, float]] = {}
    for key in _KRONOS_INFERENCE_KEYS:
        base_val = float(base.get(key, _KRONOS_INFERENCE_NEUTRAL[key]))
        eff_val = float(effective.get(key, base_val))
        tol = 0.001 if key != "inference_sample_count" else 0.5
        if abs(eff_val - base_val) >= tol:
            changed[key] = {"base": base_val, "effective": eff_val}
    return changed


def render_kronos_inference_footnote(settings: Optional[dict[str, Any]] = None) -> str:
    runtime = (settings or {}).get("harness_runtime") or {}
    overlay = runtime.get("kronos_inference_overlay") or {}
    if not overlay:
        policy = runtime.get("kronos_inference_policy") or _kronos_inference_policy(settings)
        if not policy:
            return ""
        parts = [
            f"{key}={_format_inference_value(key, float(policy[key]))}"
            for key in _KRONOS_INFERENCE_KEYS
            if key in policy
        ]
        return f"_Harness Kronos：{' · '.join(parts)}_"
    bits: list[str] = []
    for key in _KRONOS_INFERENCE_KEYS:
        meta = overlay.get(key)
        if isinstance(meta, dict) and "effective" in meta:
            eff = float(meta["effective"])
            bits.append(f"{key}={_format_inference_value(key, eff)}")
    symbol_blend = runtime.get("kronos_symbol_blend") or {}
    if symbol_blend:
        pairs = ", ".join(f"{c}={v:g}" for c, v in sorted(symbol_blend.items())[:4])
        bits.append(f"symbol_blend[{pairs}]")
    if not bits:
        return ""
    return f"_Harness Kronos：{' · '.join(bits)}_"

# -*- coding: utf-8
"""User-facing threshold/runtime values — always harness-effective for reports."""

from __future__ import annotations

from typing import Any, Literal

ThresholdFormat = Literal["int", "pct", "float"]

# policy_key, ref_key in mss_breakdown, Chinese label, display format
THRESHOLD_REF_SPECS: tuple[tuple[str, str, str, ThresholdFormat], ...] = (
    ("macro_veto", "_macro_veto_ref", "宏观否决线", "int"),
    ("aggressive_entry", "_aggressive_ref", "进攻阈值", "int"),
    ("min_cash_ratio", "_min_cash_ratio_ref", "最低现金比例", "pct"),
    ("max_price_deviation_pct", "_max_price_deviation_pct_ref", "价格锚点偏差上限", "pct"),
    ("high_position_20d", "_high_position_20d_ref", "20日高位阈值", "pct"),
    ("min_volume_ratio", "_min_volume_ratio_ref", "最低量比", "float"),
    ("max_vwap_deviation_pct", "_max_vwap_deviation_pct_ref", "VWAP偏差上限", "pct"),
)

MSS_BREAKDOWN_LABELS: dict[str, str] = {spec[1]: spec[2] for spec in THRESHOLD_REF_SPECS}

_POLICY_LABELS: dict[str, str] = {spec[0]: spec[2] for spec in THRESHOLD_REF_SPECS}


def format_threshold_display(value: float, fmt: ThresholdFormat) -> str:
    if fmt == "int":
        return f"{float(value):.0f}"
    if fmt == "pct":
        pct = float(value)
        if pct > 1.0:
            pct /= 100.0
        return f"{pct:.0%}"
    if fmt == "float":
        return f"{float(value):.2f}"
    return str(value)


def _policy_value(settings: dict[str, Any], policy_key: str) -> float:
    from agent_reach.daily_run.harness_policy import min_cash_ratio_default, threshold_default

    if policy_key == "min_cash_ratio":
        return float(min_cash_ratio_default(settings))
    return float(threshold_default(settings, policy_key))


def threshold_refs_for_display(settings: dict[str, Any]) -> dict[str, float]:
    """Effective evolved thresholds stamped into snapshot mss_breakdown refs."""
    from agent_reach.daily_run.settings import effective_settings

    eff = effective_settings(settings)
    refs: dict[str, float] = {}
    for policy_key, ref_key, _label, _fmt in THRESHOLD_REF_SPECS:
        refs[ref_key] = _policy_value(eff, policy_key)
    return refs


def apply_threshold_refs(breakdown: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    """Refresh threshold ref keys on an existing breakdown (e.g. macro daily cache)."""
    out = dict(breakdown or {})
    out.update(threshold_refs_for_display(settings))
    return out


def format_mss_breakdown_lines(breakdown: dict[str, Any]) -> list[str]:
    """Render MSS factor lines; threshold refs use friendly Chinese labels."""
    lines: list[str] = []
    ref_lines: list[str] = []
    spec_by_ref = {spec[1]: spec for spec in THRESHOLD_REF_SPECS}

    for key, value in (breakdown or {}).items():
        spec = spec_by_ref.get(key)
        if spec:
            _policy_key, _ref_key, label, fmt = spec
            ref_lines.append(f"- {label}: {format_threshold_display(float(value), fmt)}")
        elif str(key).startswith("_"):
            continue
        else:
            lines.append(f"- {key}: {value}")

    return lines + ref_lines


def format_effective_thresholds_markdown(settings: dict[str, Any]) -> str:
    """Compact harness-effective threshold summary for report footers."""
    from agent_reach.daily_run.settings import effective_settings

    eff = effective_settings(settings)
    overlay = (eff.get("harness_runtime") or {}).get("threshold_overlay") or {}
    if not overlay:
        return ""

    fmt_by_key = {spec[0]: spec[3] for spec in THRESHOLD_REF_SPECS}
    lines = ["**策略参数（harness 有效值）：**"]
    for policy_key, change in overlay.items():
        if not isinstance(change, dict):
            continue
        label = _POLICY_LABELS.get(policy_key, policy_key)
        base = change.get("base")
        eff_val = change.get("effective")
        if base is None or eff_val is None:
            continue
        fmt = fmt_by_key.get(policy_key, "float")
        eff_text = format_threshold_display(float(eff_val), fmt)
        if abs(float(eff_val) - float(base)) >= 0.005:
            base_text = format_threshold_display(float(base), fmt)
            lines.append(f"- {label}: {eff_text}（基准 {base_text}）")
        else:
            lines.append(f"- {label}: {eff_text}")
    return "\n".join(lines) if len(lines) > 1 else ""


def format_lookback_weights_pct(weights: list[float]) -> str:
    """Render lookback weight triple as 60%/25%/15%."""
    if not weights:
        return ""
    return "/".join(f"{int(round(float(w) * 100))}%" for w in weights)


def format_lookback_overlay_markdown(settings: dict[str, Any]) -> str:
    """Harness-effective lookback weights for intraday report footers."""
    from agent_reach.daily_run.settings import effective_settings

    eff = effective_settings(settings)
    overlay = (eff.get("harness_runtime") or {}).get("lookback_overlay") or {}
    block = overlay.get("lookback_weights")
    if not isinstance(block, dict):
        return ""
    base = block.get("base")
    eff_w = block.get("effective")
    if not base or not eff_w:
        return ""
    base_vals = [round(float(x), 4) for x in base]
    eff_vals = [round(float(x), 4) for x in eff_w]
    if base_vals == eff_vals:
        return ""
    return (
        f"**Lookback 权重（harness 有效值）：** "
        f"{format_lookback_weights_pct(eff_vals)}（基准 {format_lookback_weights_pct(base_vals)}）"
    )


def effective_policy_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Settings with harness overlay — use for any user-visible policy display."""
    from agent_reach.daily_run.settings import effective_settings, load_settings

    return effective_settings(settings if settings is not None else load_settings())

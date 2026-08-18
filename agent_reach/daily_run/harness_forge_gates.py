# -*- coding: utf-8
"""Numeric validation gates for domain-specific harness jobs (DSH forge-gates pattern)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ForgeGateResult:
    job: str
    passed: bool
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job": self.job,
            "passed": self.passed,
            "violations": list(self.violations),
        }


def _harness_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    if settings is None:
        try:
            from agent_reach.daily_run.settings import load_settings

            settings = load_settings()
        except Exception:
            settings = {}
    return dict((settings or {}).get("harness") or {})


def forge_gates_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = _harness_cfg(settings)
    raw = dict(cfg.get("forge_gates") or {})
    pnl_raw = dict(raw.get("pnl_target") or {})
    fc_raw = dict(raw.get("forecast_calibrate") or {})
    return {
        "enabled": raw.get("enabled", True) is not False,
        "pnl_target": {
            "max_target_pct": float(pnl_raw.get("max_target_pct") or 3.0),
            "max_target_cny": float(pnl_raw.get("max_target_cny") or 50000),
        },
        "forecast_calibrate": {
            "use_week_forecast_bounds": fc_raw.get("use_week_forecast_bounds", True) is not False,
        },
    }


def strip_forge_domain(evidence: dict[str, Any]) -> dict[str, Any]:
    if not evidence or "forge_domain" not in evidence:
        return evidence
    cleaned = dict(evidence)
    cleaned.pop("forge_domain", None)
    return cleaned


def _pnl_target_bounds(settings: Optional[dict[str, Any]], forge_cfg: dict[str, Any]) -> dict[str, float]:
    pnl_cfg = dict((settings or {}).get("pnl_target") or {})
    min_cny = float(pnl_cfg.get("min_target_cny") or 0)
    max_pct = float(forge_cfg["pnl_target"]["max_target_pct"])
    max_cny = float(forge_cfg["pnl_target"]["max_target_cny"])
    return {"min_cny": min_cny, "max_pct": max_pct, "max_cny": max_cny}


def validate_pnl_target_forge(
    domain: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> ForgeGateResult:
    cfg = forge_gates_cfg(settings)
    bounds = _pnl_target_bounds(settings, cfg)
    violations: list[str] = []

    def _check_target(row: dict[str, Any], label: str) -> None:
        if not row:
            return
        target_cny = row.get("target_pnl_cny")
        if target_cny is not None:
            cny = float(target_cny)
            if cny < bounds["min_cny"]:
                violations.append(f"{label}.target_pnl_cny {cny} < min {bounds['min_cny']}")
            if cny > bounds["max_cny"]:
                violations.append(f"{label}.target_pnl_cny {cny} > max {bounds['max_cny']}")
            if cny < 0:
                violations.append(f"{label}.target_pnl_cny must be non-negative")
        target_pct = row.get("target_pnl_pct")
        if target_pct is not None:
            pct = float(target_pct)
            if pct < 0 or pct > bounds["max_pct"]:
                violations.append(
                    f"{label}.target_pnl_pct {pct} outside [0, {bounds['max_pct']}]"
                )
        baseline = row.get("baseline_nav")
        if baseline and target_cny is not None and float(baseline) > 0:
            implied_pct = float(target_cny) / float(baseline) * 100
            if implied_pct > bounds["max_pct"]:
                violations.append(
                    f"{label} implied pct {implied_pct:.2f}% > max {bounds['max_pct']}%"
                )

    _check_target(domain.get("next_target") or {}, "next_target")
    _check_target(domain.get("evaluated") or {}, "evaluated")
    return ForgeGateResult(job="pnl_target", passed=not violations, violations=violations)


def validate_forecast_calibrate_forge(
    domain: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> ForgeGateResult:
    cfg = forge_gates_cfg(settings)
    violations: list[str] = []
    wf_cfg = dict((settings or {}).get("week_forecast") or {})
    min_vol = float(wf_cfg.get("min_vol_scale") or 0.6)
    max_vol = float(wf_cfg.get("max_vol_scale") or 1.6)
    max_bias = float(wf_cfg.get("max_bias_pct") or 3.0)

    if not cfg["forecast_calibrate"]["use_week_forecast_bounds"]:
        return ForgeGateResult(job="forecast_calibrate", passed=True)

    cal = domain.get("calibration_used") or {}
    if isinstance(cal, dict) and cal:
        vol = cal.get("vol_scale")
        if vol is not None:
            vol_f = float(vol)
            if vol_f < min_vol or vol_f > max_vol:
                violations.append(f"vol_scale {vol_f} outside [{min_vol}, {max_vol}]")
        bias = cal.get("bias_pct")
        if bias is not None:
            bias_f = float(bias)
            if abs(bias_f) > max_bias:
                violations.append(f"bias_pct {bias_f} outside ±{max_bias}")

    return ForgeGateResult(job="forecast_calibrate", passed=not violations, violations=violations)


_FORGE_JOBS = frozenset({"pnl_target", "forecast_calibrate"})


def evaluate_forge_gate(
    job: str,
    evidence: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> Optional[ForgeGateResult]:
    """Return None when forge gates disabled or job has no validator."""
    cfg = forge_gates_cfg(settings)
    if not cfg.get("enabled") or job not in _FORGE_JOBS:
        return None

    domain = evidence.get("forge_domain")
    if not isinstance(domain, dict):
        return ForgeGateResult(
            job=job,
            passed=True,
            violations=[],
        )

    if job == "pnl_target":
        return validate_pnl_target_forge(domain, settings=settings)
    if job == "forecast_calibrate":
        return validate_forecast_calibrate_forge(domain, settings=settings)
    return None


def format_forge_gate_markdown(forge_gate: dict[str, Any]) -> str:
    if not forge_gate or forge_gate.get("passed") is not False:
        return ""
    violations = forge_gate.get("violations") or []
    if not violations:
        return "- Forge 门控：数值校验未通过"
    preview = "；".join(str(v) for v in violations[:4])
    suffix = f" 等 {len(violations)} 项" if len(violations) > 4 else ""
    return f"- Forge 门控拦截：{preview}{suffix}"

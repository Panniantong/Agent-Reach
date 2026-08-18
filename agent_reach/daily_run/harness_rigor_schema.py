# -*- coding: utf-8
"""RigorQuant-inspired study.json schema validation for optimize domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class StudySchemaResult:
    passed: bool
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "violations": list(self.violations)}


def _schema_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    harness = dict((settings or {}).get("harness") or {})
    raw = dict(harness.get("rigor_schema") or {})
    return {
        "enabled": raw.get("enabled", True) is not False,
        "jobs": set(raw.get("jobs") or ["optimize"]),
        "min_trials": int(raw.get("min_trials") or 1),
        "require_metrics": list(raw.get("require_metrics") or ["total_return", "max_drawdown"]),
    }


def validate_optimize_study_schema(
    domain: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> StudySchemaResult:
    """Validate optimizer forge/rigor domain against a minimal study.json contract."""
    cfg = _schema_cfg(settings)
    violations: list[str] = []

    if domain.get("objective") in (None, ""):
        violations.append("missing objective")
    if domain.get("best_score") is None:
        violations.append("missing best_score")
    trials = int(domain.get("trials") or 0)
    if trials < cfg["min_trials"]:
        violations.append(f"trials {trials} < min {cfg['min_trials']}")

    metrics = domain.get("metrics") or {}
    if not isinstance(metrics, dict):
        violations.append("metrics must be object")
    else:
        for key in cfg["require_metrics"]:
            if metrics.get(key) is None:
                violations.append(f"metrics.{key} missing")

    params = domain.get("best_params") or {}
    if not isinstance(params, dict) or not params:
        violations.append("best_params empty")
    else:
        for key in ("macro_veto", "aggressive_entry"):
            val = params.get(key)
            if val is None:
                violations.append(f"best_params.{key} missing")
            else:
                fval = float(val)
                if fval < 10 or fval > 100:
                    violations.append(f"best_params.{key}={fval} out of bounds")

    return StudySchemaResult(passed=not violations, violations=violations)


def evaluate_study_schema(
    job: str,
    domain: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> Optional[StudySchemaResult]:
    cfg = _schema_cfg(settings)
    if not cfg["enabled"] or job not in cfg["jobs"]:
        return None
    if job == "optimize":
        return validate_optimize_study_schema(domain, settings=settings)
    return None

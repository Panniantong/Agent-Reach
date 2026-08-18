# -*- coding: utf-8
"""RigorQuant-inspired four-part pre-apply check battery for harness jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

CheckName = Literal["closure", "invariant", "boundary", "evidence"]


@dataclass
class RigorCheck:
    name: CheckName
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class RigorBatteryResult:
    job: str
    passed: bool
    checks: list[RigorCheck] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job": self.job,
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "blocking": list(self.blocking),
        }


def _rigor_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    harness = dict((settings or {}).get("harness") or {})
    raw = dict(harness.get("rigor_check") or {})
    jobs = raw.get("jobs")
    if jobs is None:
        job_set = {
            "finance_close",
            "finance_ledger",
            "finance_variance",
            "finance_close_plan",
            "optimize",
            "pnl_target",
            "forecast_calibrate",
        }
    elif isinstance(jobs, dict):
        job_set = {k for k, v in jobs.items() if v}
    else:
        job_set = set(jobs)
    block_raw = raw.get("block_on_fail")
    if block_raw is None:
        block_jobs = {"optimize"}
    elif isinstance(block_raw, dict):
        block_jobs = {k for k, v in block_raw.items() if v}
    else:
        block_jobs = set(block_raw)
    return {
        "enabled": raw.get("enabled", True) is not False,
        "jobs": job_set,
        "block_on_fail": block_jobs,
    }


def _check_closure(domain: dict[str, Any]) -> RigorCheck:
    journal = domain.get("journal") or {}
    if journal:
        ok = bool(journal.get("balanced"))
        return RigorCheck("closure", ok, f"ledger diff={journal.get('difference')}")
    variance = domain.get("variance") or {}
    reconcile = domain.get("reconcile") or {}
    if variance:
        ok = bool(variance.get("reconciled"))
        residual = variance.get("residual")
        detail = f"variance residual={residual}"
        return RigorCheck("closure", ok, detail)
    if reconcile:
        ok = bool(reconcile.get("reconciled"))
        diff = reconcile.get("difference")
        return RigorCheck("closure", ok, f"reconcile diff={diff}")
    metrics = domain.get("metrics") or {}
    if metrics:
        total = metrics.get("total_return")
        ok = total is not None
        return RigorCheck("closure", ok, f"backtest total_return={total}")
    return RigorCheck("closure", True, "no closure domain")


def _check_invariant(domain: dict[str, Any]) -> RigorCheck:
    risk = domain.get("risk") or {}
    flags = list(risk.get("flags") or [])
    hard = [f for f in flags if "超过上限" in f or "低于下限" in f]
    return RigorCheck("invariant", not hard, "; ".join(hard) if hard else "risk within policy")


def _check_boundary(domain: dict[str, Any], *, job: str) -> RigorCheck:
    if job == "optimize":
        params = domain.get("best_params") or {}
        veto = params.get("macro_veto")
        entry = params.get("aggressive_entry")
        bad: list[str] = []
        for key, val in (("macro_veto", veto), ("aggressive_entry", entry)):
            if val is None:
                continue
            fval = float(val)
            if fval < 10 or fval > 100:
                bad.append(f"{key}={fval}")
        weights = params.get("mss_weights")
        if isinstance(weights, dict) and weights:
            total = sum(float(v) for v in weights.values())
            if abs(total - 1.0) > 0.05:
                bad.append(f"mss_weights sum={total:.3f}")
        return RigorCheck("boundary", not bad, "; ".join(bad) if bad else "optimizer bounds ok")
    if job in {"pnl_target", "forecast_calibrate"}:
        return RigorCheck("boundary", True, "handled by forge_gates")
    return RigorCheck("boundary", True, "default ok")


def _check_evidence(domain: dict[str, Any], *, job: str) -> RigorCheck:
    if job == "finance_close":
        summary = domain.get("portfolio_summary") or {}
        required = ("as_of", "end_total")
        missing = [k for k in required if summary.get(k) in (None, "")]
        if missing:
            return RigorCheck("evidence", False, f"missing {','.join(missing)}")
        return RigorCheck("evidence", True, "portfolio fields present")
    if job in {"finance_variance", "finance_close_plan"}:
        report = domain.get("report") or {}
        if not report.get("week_start") or not report.get("week_end"):
            return RigorCheck("evidence", False, "missing week range")
        return RigorCheck("evidence", True, "weekly report present")
    if job == "finance_ledger":
        journal = domain.get("journal") or {}
        if not journal.get("actions_checked") and not (domain.get("trades") or []):
            return RigorCheck("evidence", True, "no ledger trades")
        if journal.get("actions_checked", 0) <= 0:
            return RigorCheck("evidence", False, "no ledger actions")
        return RigorCheck("evidence", True, f"actions={journal.get('actions_checked')}")
    if job == "optimize":
        result = domain
        if not result.get("trials"):
            return RigorCheck("evidence", False, "no optimizer trials")
        if result.get("best_score") is None:
            return RigorCheck("evidence", False, "missing best_score")
        return RigorCheck("evidence", True, f"trials={result.get('trials')}")
    return RigorCheck("evidence", True, "default ok")


def evaluate_rigor_battery(
    job: str,
    domain: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> Optional[RigorBatteryResult]:
    cfg = _rigor_cfg(settings)
    if not cfg.get("enabled") or job not in cfg.get("jobs", set()):
        return None

    checks = [
        _check_closure(domain),
        _check_invariant(domain),
        _check_boundary(domain, job=job),
        _check_evidence(domain, job=job),
    ]
    blocking = [f"{c.name}:{c.detail}" for c in checks if not c.passed and c.detail]
    return RigorBatteryResult(
        job=job,
        passed=all(c.passed for c in checks),
        checks=checks,
        blocking=blocking,
    )


def rigor_blocks_refine(result: Optional[RigorBatteryResult], *, settings: Optional[dict[str, Any]] = None) -> bool:
    if result is None or result.passed:
        return False
    cfg = _rigor_cfg(settings)
    return result.job in cfg.get("block_on_fail", set())


def format_rigor_markdown(rigor: dict[str, Any]) -> str:
    if not rigor or rigor.get("passed") is not False:
        return ""
    blocking = rigor.get("blocking") or []
    preview = "；".join(str(x) for x in blocking[:3])
    suffix = f" 等 {len(blocking)} 项" if len(blocking) > 3 else ""
    return f"- Rigor 校验拦截：{preview}{suffix}"

# -*- coding: utf-8
"""Harness-evolved intraday trend, expected-return, audit, and Kronos guards."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.snapshot_builder import _normalize_code

_DEFAULT_BUY_TRENDS = ("rising", "turning_up")
_DEFAULT_SELL_TRENDS = ("falling", "turning_down")


def _intraday_cfg(settings: dict[str, Any]) -> dict[str, Any]:
    return dict(settings.get("intraday") or {})


def _runtime_policy(settings: dict[str, Any], key: str) -> dict[str, Any]:
    runtime = settings.get("harness_runtime") or {}
    policy = runtime.get(key)
    return dict(policy) if isinstance(policy, dict) else {}


def trend_policy(settings: dict[str, Any]) -> dict[str, Any]:
    runtime = settings.get("harness_runtime") or {}
    if runtime.get("trend_policy"):
        return dict(runtime["trend_policy"])
    harness = settings.get("harness") or {}
    if harness.get("enabled") is False or harness.get("runtime_overlay") is False:
        return _inline_trend_policy(settings)
    if not harness and _intraday_cfg(settings):
        return _inline_trend_policy(settings)
    if _overlay_enabled(settings):
        from agent_reach.daily_run.harness import load_harness
        from agent_reach.daily_run.harness_policy import resolve_harness_trend_policy

        return resolve_harness_trend_policy(load_harness(), settings=settings)
    return _inline_trend_policy(settings)


def _inline_trend_policy(settings: dict[str, Any]) -> dict[str, Any]:
    cfg = _intraday_cfg(settings)
    return {
        "trend_min_points": float(cfg.get("trend_min_points", 2)),
        "trend_delta_threshold": float(cfg.get("trend_delta_threshold", 1.0)),
        "buy_trends": list(cfg.get("buy_trends") or _DEFAULT_BUY_TRENDS),
        "sell_trends": list(cfg.get("sell_trends") or _DEFAULT_SELL_TRENDS),
    }


def expected_return_policy(settings: dict[str, Any]) -> dict[str, float]:
    from agent_reach.daily_run.harness_policy import resolve_harness_expected_return_policy

    if settings.get("harness_runtime", {}).get("expected_return_policy"):
        raw = settings["harness_runtime"]["expected_return_policy"]
        return {k: float(v) for k, v in raw.items()}
    if (settings.get("harness") or {}).get("runtime_overlay", True) is not False:
        from agent_reach.daily_run.harness import load_harness

        return resolve_harness_expected_return_policy(load_harness(), settings=settings)
    cfg = _intraday_cfg(settings)
    exp = dict(cfg.get("expected_return") or {})
    return {
        "exp_return_base": float(exp.get("base", 0.015)),
        "exp_return_slope": float(exp.get("slope", 0.001)),
        "exp_return_veto": float(exp.get("veto", -0.02)),
        "exp_return_neutral": float(exp.get("neutral", 0.005)),
    }


def intraday_audit_policy(settings: dict[str, Any]) -> dict[str, float]:
    from agent_reach.daily_run.harness_policy import resolve_harness_intraday_audit_policy

    if settings.get("harness_runtime", {}).get("intraday_audit_policy"):
        raw = settings["harness_runtime"]["intraday_audit_policy"]
        return {k: float(v) for k, v in raw.items()}
    if (settings.get("harness") or {}).get("runtime_overlay", True) is not False:
        from agent_reach.daily_run.harness import load_harness

        return resolve_harness_intraday_audit_policy(load_harness(), settings=settings)
    audit = dict(settings.get("data_audit") or {})
    return {
        "intraday_block_on_audit_fail": 1.0 if audit.get("intraday_block_on_audit_fail") else 0.0,
        "min_quote_coverage_pct": float(audit.get("min_quote_coverage_pct", 0.8)),
    }


def detect_mss_trend(
    scans: list[dict[str, Any]],
    settings: Optional[dict[str, Any]] = None,
    *,
    min_points: Optional[int] = None,
) -> str:
    """Trend label from recent scan MSS values (harness-evolved thresholds)."""
    policy = trend_policy(settings or {}) if settings is not None else {}
    min_pts = int(min_points if min_points is not None else policy.get("trend_min_points", 2))
    delta_thr = float(policy.get("trend_delta_threshold", 1.0))

    if len(scans) < min_pts:
        return "insufficient"

    values = [float(s.get("mss_final", 0)) for s in scans[-3:]]
    if len(values) >= 3:
        d1 = values[-1] - values[-2]
        d2 = values[-2] - values[-3]
        if d1 > delta_thr and d2 > 0:
            return "turning_up"
        if d1 < -delta_thr and d2 < 0:
            return "turning_down"
        if all(values[i] >= values[i - 1] for i in range(1, len(values))):
            return "rising"
        if all(values[i] <= values[i - 1] for i in range(1, len(values))):
            return "falling"
        return "mixed"

    delta = values[-1] - values[-2]
    if delta > delta_thr:
        return "rising"
    if delta < -delta_thr:
        return "falling"
    return "flat"


def trend_allows_buy(settings: dict[str, Any], trend: str) -> bool:
    allowed = trend_policy(settings).get("buy_trends") or list(_DEFAULT_BUY_TRENDS)
    return str(trend or "") in {str(x) for x in allowed}


def trend_allows_defensive_sell(settings: dict[str, Any], trend: str) -> bool:
    allowed = trend_policy(settings).get("sell_trends") or list(_DEFAULT_SELL_TRENDS)
    return str(trend or "") in {str(x) for x in allowed}


def estimate_expected_return(
    mss: float,
    aggressive: float,
    macro_veto: float,
    settings: dict[str, Any],
) -> float:
    policy = expected_return_policy(settings)
    base = float(policy.get("exp_return_base", 0.015))
    slope = float(policy.get("exp_return_slope", 0.001))
    veto = float(policy.get("exp_return_veto", -0.02))
    neutral = float(policy.get("exp_return_neutral", 0.005))
    if mss >= aggressive:
        return base + (mss - aggressive) * slope
    if mss <= macro_veto:
        return veto
    return neutral


def intraday_audit_block_reason(
    settings: dict[str, Any],
    report: dict[str, Any],
) -> Optional[str]:
    policy = intraday_audit_policy(settings)
    if policy.get("intraday_block_on_audit_fail", 0.0) <= 0.5:
        return None
    if report.get("audit_passed") is False:
        return "盘中数据审计未通过，暂缓调仓"
    warnings = list(report.get("audit_warnings") or [])
    min_cov = float(policy.get("min_quote_coverage_pct", 0.8))
    for warning in warnings:
        text = str(warning)
        if "行情覆盖率" in text and "低于阈值" in text:
            return f"行情覆盖率不足（阈值 {min_cov:.0%}），暂缓调仓"
    return None


def kronos_buy_block_reason(settings: dict[str, Any], code: str) -> Optional[str]:
    cfg = _intraday_cfg(settings)
    if cfg.get("kronos_bearish_block_buy") is False:
        return None
    norm = _normalize_code(str(code or ""))
    if not norm:
        return None
    runtime = settings.get("harness_runtime") or {}
    bearish = runtime.get("kronos_bearish") or {}
    pct = bearish.get(norm)
    if pct is None:
        return None
    if float(pct) > 0:
        return f"Kronos 偏弱 {float(pct):.1f}%，暂缓买入"
    return None

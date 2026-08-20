# -*- coding: utf-8
"""DeepSeek numeric optimizers for harness threshold / pnl_target / forecast evolution."""

from __future__ import annotations

import re
from typing import Any, Optional

from agent_reach.daily_run.harness_policy import (
    aggressive_entry_default,
    forecast_int_default,
    macro_veto_default,
    min_cash_ratio_default,
    pnl_target_policy_default,
    runtime_float_default,
)

_THRESHOLD_PREFIX = "what-if DeepSeek 阈值最优"
_THRESHOLD_RE = re.compile(
    r"what-if DeepSeek 阈值最优：macro_veto=([\d.]+)\s+aggressive_entry=([\d.]+)\s+"
    r"min_cash_ratio=([\d.]+)(?:\s+friction_min_return_pct=([\d.]+))?"
    r"(?:\s+trend_min_points=([\d.]+))?",
    re.IGNORECASE,
)

_PNL_TARGET_PREFIX = "what-if DeepSeek pnl_target最优"
_PNL_TARGET_RE = re.compile(
    r"what-if DeepSeek pnl_target最优：base_target_pct=([\d.]+)\s+"
    r"streak_bonus_pct=([\d.]+)\s+miss_recovery_factor=([\d.]+)",
    re.IGNORECASE,
)

_FORECAST_PREFIX = "what-if DeepSeek forecast最优"
_FORECAST_RE = re.compile(
    r"what-if DeepSeek forecast最优：base_spread=([\d.]+)\s+vol_multiplier=([\d.]+)",
    re.IGNORECASE,
)

_THRESHOLD_BOUNDS = {
    "macro_veto": (25.0, 50.0),
    "aggressive_entry": (40.0, 60.0),
    "min_cash_ratio": (0.0, 0.85),
    "friction_min_return_pct": (0.003, 0.02),
    "trend_min_points": (2.0, 5.0),
}

_PNL_TARGET_BOUNDS = {
    "base_target_pct": (0.05, 5.0),
    "streak_bonus_pct": (0.0, 50.0),
    "miss_recovery_factor": (0.3, 1.0),
}

_FORECAST_BOUNDS = {
    "base_spread": (6.0, 15.0),
    "vol_multiplier": (4.0, 12.0),
}


def _section_cfg(settings: Optional[dict[str, Any]], section: str) -> dict[str, Any]:
    root = dict((settings or {}).get("harness_evolution") or {})
    sec = dict((settings or {}).get(section) or {})
    llm_refine = dict((settings or {}).get("harness") or {}).get("llm_refine") or {}
    sell_cfg = dict((settings or {}).get("sell_rules_whatif") or {})
    if root.get("llm_optimize") is False or sec.get("llm_optimize") is False:
        return {"llm_optimize": False}
    provider = str(
        sec.get("llm_provider")
        or root.get("llm_provider")
        or sell_cfg.get("llm_provider")
        or llm_refine.get("provider")
        or "deepseek"
    )
    return {
        "llm_optimize": sec.get("llm_optimize", root.get("llm_optimize", True)),
        "llm_provider": provider,
        "llm_model": sec.get("llm_model") or root.get("llm_model") or llm_refine.get("model"),
        "llm_timeout_seconds": int(
            sec.get("llm_timeout_seconds")
            or root.get("llm_timeout_seconds")
            or llm_refine.get("timeout_seconds")
            or 45
        ),
        "llm_temperature": float(
            sec.get("llm_temperature") or root.get("llm_temperature") or 0.1
        ),
    }


def _clamp_values(raw: dict[str, Any], bounds: dict[str, tuple[float, float]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, (lo, hi) in bounds.items():
        val = raw.get(key)
        if val is None:
            continue
        out[key] = round(max(lo, min(hi, float(val))), 3)
    return out


def _find_parsed_in_state(
    state: Any,
    *,
    settings: dict[str, Any],
    parser,
) -> Optional[dict[str, float]]:
    from agent_reach.daily_run.harness_policy import _collect_text_blobs, _overlay_sources

    for blob in _collect_text_blobs(
        state, sources=_overlay_sources(settings), kind="policy", settings=settings
    ):
        parsed = parser(blob)
        if parsed:
            return parsed
    return None


def format_threshold_policy_line(ratios: dict[str, float], *, rationale: str = "") -> str:
    mv = ratios.get("macro_veto")
    ae = ratios.get("aggressive_entry")
    mc = ratios.get("min_cash_ratio")
    if mv is None or ae is None or mc is None:
        return ""
    line = (
        f"{_THRESHOLD_PREFIX}：macro_veto={float(mv):.2f} "
        f"aggressive_entry={float(ae):.2f} min_cash_ratio={float(mc):.2f}"
    )
    fr = ratios.get("friction_min_return_pct")
    tp = ratios.get("trend_min_points")
    if fr is not None:
        line += f" friction_min_return_pct={float(fr):.4f}"
    if tp is not None:
        line += f" trend_min_points={float(tp):.1f}"
    reason = str(rationale or "").strip()
    if reason:
        line += f" — {reason[:120]}"
    return line


def parse_threshold_policy_line(text: str) -> Optional[dict[str, float]]:
    match = _THRESHOLD_RE.search(str(text or ""))
    if not match:
        return None
    raw = {
        "macro_veto": float(match.group(1)),
        "aggressive_entry": float(match.group(2)),
        "min_cash_ratio": float(match.group(3)),
    }
    if match.group(4):
        raw["friction_min_return_pct"] = float(match.group(4))
    if match.group(5):
        raw["trend_min_points"] = float(match.group(5))
    parsed = _clamp_values(raw, _THRESHOLD_BOUNDS)
    if parsed.get("aggressive_entry", 0) <= parsed.get("macro_veto", 0):
        parsed["aggressive_entry"] = float(parsed["macro_veto"]) + 2.0
    return parsed


def format_pnl_target_policy_line(ratios: dict[str, float], *, rationale: str = "") -> str:
    bp = ratios.get("base_target_pct")
    sb = ratios.get("streak_bonus_pct")
    mr = ratios.get("miss_recovery_factor")
    if bp is None or sb is None or mr is None:
        return ""
    line = (
        f"{_PNL_TARGET_PREFIX}：base_target_pct={float(bp):.2f} "
        f"streak_bonus_pct={float(sb):.1f} miss_recovery_factor={float(mr):.2f}"
    )
    reason = str(rationale or "").strip()
    if reason:
        line += f" — {reason[:120]}"
    return line


def parse_pnl_target_policy_line(text: str) -> Optional[dict[str, float]]:
    match = _PNL_TARGET_RE.search(str(text or ""))
    if not match:
        return None
    return _clamp_values(
        {
            "base_target_pct": float(match.group(1)),
            "streak_bonus_pct": float(match.group(2)),
            "miss_recovery_factor": float(match.group(3)),
        },
        _PNL_TARGET_BOUNDS,
    )


def format_forecast_policy_line(ratios: dict[str, float], *, rationale: str = "") -> str:
    bs = ratios.get("base_spread")
    vm = ratios.get("vol_multiplier")
    if bs is None or vm is None:
        return ""
    line = (
        f"{_FORECAST_PREFIX}：base_spread={float(bs):.1f} "
        f"vol_multiplier={float(vm):.1f}"
    )
    reason = str(rationale or "").strip()
    if reason:
        line += f" — {reason[:120]}"
    return line


def parse_forecast_policy_line(text: str) -> Optional[dict[str, float]]:
    match = _FORECAST_RE.search(str(text or ""))
    if not match:
        return None
    return _clamp_values(
        {"base_spread": float(match.group(1)), "vol_multiplier": float(match.group(2))},
        _FORECAST_BOUNDS,
    )


def build_weekly_threshold_payload(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = settings or {}
    sell = report.get("sell_rules_whatif") or {}
    buy = report.get("buy_rules_whatif") or {}
    return {
        "week_start": report.get("week_start"),
        "week_end": report.get("week_end"),
        "weekly_pnl": report.get("weekly_pnl"),
        "weekly_pnl_pct": report.get("weekly_pnl_pct"),
        "cash_ratio": report.get("cash_ratio"),
        "sell_whatif": {
            "realized_pnl_delta": sell.get("realized_pnl_delta"),
            "skipped": sell.get("skipped"),
        },
        "buy_whatif": {
            "buy_notional_delta": buy.get("buy_notional_delta"),
            "skipped": buy.get("skipped"),
        },
        "current": {
            "macro_veto": macro_veto_default(cfg),
            "aggressive_entry": aggressive_entry_default(cfg),
            "min_cash_ratio": min_cash_ratio_default(cfg),
            "friction_min_return_pct": runtime_float_default(cfg, "schedule", "friction_min_return_pct"),
            "trend_min_points": runtime_float_default(cfg, "intraday", "trend_min_points"),
        },
        "constraints": {k: list(v) for k, v in _THRESHOLD_BOUNDS.items()},
        "objective": (
            "根据周度净值与买卖 what-if，给出下一周 macro_veto / aggressive_entry / "
            "min_cash_ratio / friction_min_return_pct / trend_min_points 最优解；"
            "aggressive_entry 必须高于 macro_veto"
        ),
    }


def optimize_weekly_threshold_with_deepseek(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _section_cfg(settings, "weekly_threshold")
    if not cfg.get("llm_optimize"):
        return {"skipped": True, "reason": "harness_evolution.weekly_threshold disabled"}

    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(cfg.get("llm_provider") or "deepseek")
    if not resolve_chat_provider(provider):
        return {"skipped": True, "reason": "no llm provider (set DEEPSEEK_API_KEY)"}

    import json

    payload = build_weekly_threshold_payload(report, settings=settings)
    result = chat_json(
        system=(
            "你是 A 股 daily-run harness 阈值优化器。输出 JSON："
            '{"macro_veto":42,"aggressive_entry":52,"min_cash_ratio":0.35,'
            '"friction_min_return_pct":0.006,"trend_min_points":3,'
            '"rationale":"中文理由","confidence":0.0-1.0}。'
            "规则：1) 各字段在 constraints 内；2) aggressive_entry > macro_veto；"
            "3) 周度亏损或 defensive 语境可抬高 min_cash_ratio、抬高 macro_veto；"
            "4) 买卖 what-if 显示错失机会时可略降 aggressive_entry / friction；"
            "5) rationale 一句话。"
        ),
        user=json.dumps(payload, ensure_ascii=False),
        provider=provider,
        model=cfg.get("llm_model") or None,
        temperature=float(cfg.get("llm_temperature") or 0.1),
        timeout=int(cfg.get("llm_timeout_seconds") or 45),
        max_tokens=512,
    )
    if not isinstance(result, dict):
        return {"skipped": True, "reason": "llm returned no json"}

    ratios = _clamp_values(result, _THRESHOLD_BOUNDS)
    if len(ratios) < 3:
        return {"skipped": True, "reason": "llm ratios incomplete", "raw": result}
    if ratios.get("aggressive_entry", 0) <= ratios.get("macro_veto", 0):
        ratios["aggressive_entry"] = float(ratios["macro_veto"]) + 2.0

    rationale = str(result.get("rationale") or "").strip()
    policy_line = format_threshold_policy_line(ratios, rationale=rationale)
    evidence = {
        "memory": [
            (
                f"DeepSeek 阈值最优：veto={ratios['macro_veto']:.0f} "
                f"entry={ratios['aggressive_entry']:.0f} "
                f"cash={ratios['min_cash_ratio']:.0%}"
            )
        ],
        "policy": [policy_line] if policy_line else [],
        "playbook": ["DeepSeek 阈值最优解已写入 harness policy，runtime 直接采用"],
        "plan": ["weekly：验证 macro_veto/aggressive_entry 与盘中成交对齐"],
        "summary": f"threshold_llm veto={ratios['macro_veto']:.1f}",
        "llm_optimal": {**ratios, "rationale": rationale},
    }
    return {
        "skipped": False,
        "planner": "deepseek",
        "provider": provider,
        "optimal": ratios,
        "evidence": evidence,
        "raw": result,
    }


def build_pnl_target_payload(
    cycle: dict[str, Any],
    *,
    portfolio_summary: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = settings or {}
    pf = portfolio_summary or {}
    evaluated = cycle.get("evaluated") or {}
    return {
        "as_of": pf.get("as_of"),
        "daily_pnl": pf.get("daily_pnl"),
        "daily_pnl_pct": pf.get("daily_pnl_pct"),
        "evaluated": evaluated,
        "next_target": cycle.get("next_target"),
        "current": {
            "base_target_pct": pnl_target_policy_default(cfg, "base_target_pct"),
            "streak_bonus_pct": pnl_target_policy_default(cfg, "streak_bonus_pct"),
            "miss_recovery_factor": pnl_target_policy_default(cfg, "miss_recovery_factor"),
        },
        "constraints": {k: list(v) for k, v in _PNL_TARGET_BOUNDS.items()},
        "objective": "根据盈亏目标 hit/miss 与当日净值，给出下一交易日 pnl_target 参数最优解",
    }


def optimize_pnl_target_with_deepseek(
    cycle: dict[str, Any],
    *,
    portfolio_summary: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _section_cfg(settings, "pnl_target")
    if not cfg.get("llm_optimize"):
        return {"skipped": True, "reason": "harness_evolution.pnl_target disabled"}
    if cycle.get("skipped"):
        return {"skipped": True, "reason": "pnl_target cycle skipped"}

    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(cfg.get("llm_provider") or "deepseek")
    if not resolve_chat_provider(provider):
        return {"skipped": True, "reason": "no llm provider (set DEEPSEEK_API_KEY)"}

    import json

    payload = build_pnl_target_payload(cycle, portfolio_summary=portfolio_summary, settings=settings)
    result = chat_json(
        system=(
            "你是 daily-run harness 盈亏目标优化器。输出 JSON："
            '{"base_target_pct":0.55,"streak_bonus_pct":12,"miss_recovery_factor":0.85,'
            '"rationale":"中文理由","confidence":0.0-1.0}。'
            "规则：1) 在 constraints 内；2) hit 时可略升 base_target_pct / streak_bonus；"
            "3) miss 时略降 base_target_pct 或 miss_recovery_factor；4) rationale 一句话。"
        ),
        user=json.dumps(payload, ensure_ascii=False),
        provider=provider,
        model=cfg.get("llm_model") or None,
        temperature=float(cfg.get("llm_temperature") or 0.1),
        timeout=int(cfg.get("llm_timeout_seconds") or 45),
        max_tokens=512,
    )
    if not isinstance(result, dict):
        return {"skipped": True, "reason": "llm returned no json"}

    ratios = _clamp_values(result, _PNL_TARGET_BOUNDS)
    if len(ratios) < 3:
        return {"skipped": True, "reason": "llm ratios incomplete", "raw": result}

    rationale = str(result.get("rationale") or "").strip()
    policy_line = format_pnl_target_policy_line(ratios, rationale=rationale)
    evidence = {
        "memory": [
            f"DeepSeek pnl_target 最优：base={ratios['base_target_pct']:.2f}% "
            f"bonus={ratios['streak_bonus_pct']:.0f}% "
            f"recovery={ratios['miss_recovery_factor']:.2f}"
        ],
        "policy": [policy_line] if policy_line else [],
        "playbook": ["DeepSeek pnl_target 最优解已写入 harness policy"],
        "plan": ["close：验证下一交易日 pnl_target 与收盘净值对齐"],
        "summary": f"pnl_target_llm base={ratios['base_target_pct']:.2f}",
        "llm_optimal": {**ratios, "rationale": rationale},
    }
    return {
        "skipped": False,
        "planner": "deepseek",
        "provider": provider,
        "optimal": ratios,
        "evidence": evidence,
        "raw": result,
    }


def build_forecast_calibrate_payload(
    forecast: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = settings or {}
    cal = forecast.get("calibration_used") or {}
    div_count = 0
    for sym in (forecast.get("symbols") or {}).values():
        div_count += len(sym.get("kronos_divergence_days") or [])
    return {
        "week_start": forecast.get("week_start"),
        "week_end": forecast.get("week_end"),
        "calibration_used": cal,
        "divergence_symbol_days": div_count,
        "notes": (forecast.get("notes") or [])[:5],
        "current": {
            "base_spread": forecast_int_default(cfg, "base_spread"),
            "vol_multiplier": forecast_int_default(cfg, "vol_multiplier"),
        },
        "constraints": {k: list(v) for k, v in _FORECAST_BOUNDS.items()},
        "objective": "根据 Kronos/MSS 校准与分歧日，给出 base_spread / vol_multiplier 最优解",
    }


def optimize_forecast_calibrate_with_deepseek(
    forecast: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _section_cfg(settings, "forecast_calibrate")
    if not cfg.get("llm_optimize"):
        return {"skipped": True, "reason": "harness_evolution.forecast_calibrate disabled"}

    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(cfg.get("llm_provider") or "deepseek")
    if not resolve_chat_provider(provider):
        return {"skipped": True, "reason": "no llm provider (set DEEPSEEK_API_KEY)"}

    import json

    payload = build_forecast_calibrate_payload(forecast, settings=settings)
    result = chat_json(
        system=(
            "你是 daily-run harness MSS 预测校准优化器。输出 JSON："
            '{"base_spread":9,"vol_multiplier":6.5,"rationale":"中文理由","confidence":0.0-1.0}。'
            "规则：1) 在 constraints 内；2) 预测偏离/分歧多时可增大 base_spread 或 vol_multiplier；"
            "3) 校准偏保守时可略缩小；4) rationale 一句话。"
        ),
        user=json.dumps(payload, ensure_ascii=False),
        provider=provider,
        model=cfg.get("llm_model") or None,
        temperature=float(cfg.get("llm_temperature") or 0.1),
        timeout=int(cfg.get("llm_timeout_seconds") or 45),
        max_tokens=512,
    )
    if not isinstance(result, dict):
        return {"skipped": True, "reason": "llm returned no json"}

    ratios = _clamp_values(result, _FORECAST_BOUNDS)
    if len(ratios) < 2:
        return {"skipped": True, "reason": "llm ratios incomplete", "raw": result}

    rationale = str(result.get("rationale") or "").strip()
    policy_line = format_forecast_policy_line(ratios, rationale=rationale)
    evidence = {
        "memory": [
            f"DeepSeek forecast 最优：base_spread={ratios['base_spread']:.1f} "
            f"vol_multiplier={ratios['vol_multiplier']:.1f}"
        ],
        "policy": [policy_line] if policy_line else [],
        "playbook": ["DeepSeek forecast 最优解已写入 harness policy"],
        "plan": ["forecast：验证 MSS 区间与 Kronos 路径对齐"],
        "summary": f"forecast_llm spread={ratios['base_spread']:.1f}",
        "llm_optimal": {**ratios, "rationale": rationale},
    }
    return {
        "skipped": False,
        "planner": "deepseek",
        "provider": provider,
        "optimal": ratios,
        "evidence": evidence,
        "raw": result,
    }


def apply_threshold_llm_optimal_to_flat(
    merged: dict[str, float],
    state: Any,
    *,
    settings: dict[str, Any],
) -> bool:
    from agent_reach.daily_run.harness_policy import evolution_mode

    optimal = _find_parsed_in_state(state, settings=settings, parser=parse_threshold_policy_line)
    if not optimal:
        return False
    key_map = {
        "macro_veto": "macro_veto",
        "aggressive_entry": "aggressive_entry",
        "min_cash_ratio": "min_cash_ratio",
        "friction_min_return_pct": "friction_min_return_pct",
        "trend_min_points": "trend_min_points",
    }
    applied = False
    for src, dst in key_map.items():
        if src not in optimal:
            continue
        if evolution_mode(settings, dst) == "harness" or dst in (
            "friction_min_return_pct",
            "trend_min_points",
        ):
            merged[dst] = optimal[src]
            applied = True
    return applied


def apply_pnl_target_llm_optimal_to_policy(
    merged: dict[str, float],
    state: Any,
    *,
    settings: dict[str, Any],
) -> bool:
    from agent_reach.daily_run.harness_policy import evolution_mode

    optimal = _find_parsed_in_state(state, settings=settings, parser=parse_pnl_target_policy_line)
    if not optimal:
        return False
    applied = False
    for key in ("base_target_pct", "streak_bonus_pct", "miss_recovery_factor"):
        if key in optimal and evolution_mode(settings, key) == "harness":
            merged[key] = optimal[key]
            applied = True
    return applied


def apply_forecast_llm_optimal_to_flat(
    merged: dict[str, float],
    state: Any,
    *,
    settings: dict[str, Any],
) -> bool:
    from agent_reach.daily_run.harness_policy import evolution_mode

    optimal = _find_parsed_in_state(state, settings=settings, parser=parse_forecast_policy_line)
    if not optimal:
        return False
    applied = False
    for key in ("base_spread", "vol_multiplier"):
        if key in optimal and evolution_mode(settings, key) == "harness":
            merged[key] = optimal[key]
            applied = True
    return applied


def apply_weekly_harness_llm_refinement(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Weekly DeepSeek threshold optimizer → harness policy."""
    from agent_reach.daily_run.harness_skill_base import apply_skill_refinement, merge_harness_evidence

    opt = optimize_weekly_threshold_with_deepseek(report, settings=settings)
    if opt.get("skipped"):
        return {**opt, "job": "harness_threshold"}
    evidence = dict(opt.get("evidence") or {})
    evidence["rigor_domain"] = {
        "optimal": opt.get("optimal"),
        "weekly_pnl": report.get("weekly_pnl"),
        "week_start": report.get("week_start"),
        "week_end": report.get("week_end"),
    }
    result = apply_skill_refinement("harness_threshold", evidence, settings=settings)
    result["llm_optimize"] = {
        "skipped": False,
        "planner": opt.get("planner"),
        "optimal": opt.get("optimal"),
        "provider": opt.get("provider"),
    }
    return result

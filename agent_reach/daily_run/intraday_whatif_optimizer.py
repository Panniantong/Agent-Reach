# -*- coding: utf-8
"""DeepSeek optimizer for intraday friction/trend harness evolution."""

from __future__ import annotations

import re
from typing import Any, Optional

from agent_reach.daily_run.harness_policy import runtime_float_default, trend_policy_default

_FRICTION_PREFIX = "what-if DeepSeek 摩擦趋势最优"
_FRICTION_RE = re.compile(
    r"what-if DeepSeek 摩擦趋势最优：friction_min_return_pct=([\d.]+)\s+"
    r"trend_min_points=([\d.]+)\s+trend_delta_threshold=([\d.]+)",
    re.IGNORECASE,
)

_FRICTION_BOUNDS = {
    "friction_min_return_pct": (0.003, 0.012),
    "trend_min_points": (2.0, 5.0),
    "trend_delta_threshold": (0.5, 3.0),
}


def _section_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    root = dict((settings or {}).get("harness_evolution") or {})
    sec = dict((settings or {}).get("intraday_whatif") or {})
    sell_cfg = dict((settings or {}).get("sell_rules_whatif") or {})
    llm_refine = dict((settings or {}).get("harness") or {}).get("llm_refine") or {}
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
        "llm_temperature": float(sec.get("llm_temperature") or root.get("llm_temperature") or 0.1),
    }


def _clamp_values(raw: dict[str, Any], bounds: dict[str, tuple[float, float]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, (lo, hi) in bounds.items():
        val = raw.get(key)
        if val is None:
            continue
        out[key] = round(max(lo, min(hi, float(val))), 3)
    return out


def format_intraday_friction_policy_line(ratios: dict[str, float], *, rationale: str = "") -> str:
    fr = ratios.get("friction_min_return_pct")
    tp = ratios.get("trend_min_points")
    td = ratios.get("trend_delta_threshold")
    if fr is None or tp is None or td is None:
        return ""
    line = (
        f"{_FRICTION_PREFIX}：friction_min_return_pct={float(fr):.4f} "
        f"trend_min_points={float(tp):.1f} trend_delta_threshold={float(td):.1f}"
    )
    reason = str(rationale or "").strip()
    if reason:
        line += f" — {reason[:120]}"
    return line


def parse_intraday_friction_policy_line(text: str) -> Optional[dict[str, float]]:
    match = _FRICTION_RE.search(str(text or ""))
    if not match:
        return None
    return _clamp_values(
        {
            "friction_min_return_pct": float(match.group(1)),
            "trend_min_points": float(match.group(2)),
            "trend_delta_threshold": float(match.group(3)),
        },
        _FRICTION_BOUNDS,
    )


def _find_parsed_in_state(state: Any, *, settings: dict[str, Any]) -> Optional[dict[str, float]]:
    from agent_reach.daily_run.harness_policy import _collect_text_blobs, _overlay_sources

    for blob in _collect_text_blobs(
        state, sources=_overlay_sources(settings), kind="policy", settings=settings
    ):
        parsed = parse_intraday_friction_policy_line(blob)
        if parsed:
            return parsed
    return None


def build_intraday_friction_optimize_payload(
    portfolio_summary: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = settings or {}
    whatif = portfolio_summary.get("intraday_friction_whatif") or {}
    return {
        "as_of": portfolio_summary.get("as_of"),
        "daily_pnl": portfolio_summary.get("daily_pnl"),
        "daily_pnl_pct": portfolio_summary.get("daily_pnl_pct"),
        "whatif": {
            "friction_blocked_actual": whatif.get("friction_blocked_actual"),
            "friction_would_pass": whatif.get("friction_would_pass"),
            "trend_mismatch": whatif.get("trend_mismatch"),
            "actual_buy_count": whatif.get("actual_buy_count"),
            "evolved_buy_count": whatif.get("evolved_buy_count"),
            "rows": (whatif.get("rows") or [])[:8],
        },
        "current": {
            "friction_min_return_pct": runtime_float_default(cfg, "trading", "friction_min_return_pct"),
            "trend_min_points": trend_policy_default(cfg, "trend_min_points"),
            "trend_delta_threshold": trend_policy_default(cfg, "trend_delta_threshold"),
        },
        "constraints": {k: list(v) for k, v in _FRICTION_BOUNDS.items()},
        "objective": (
            "根据盘中摩擦/趋势 what-if，给出 friction_min_return_pct / trend_min_points / "
            "trend_delta_threshold 最优解；错失买入多时可略降 friction，趋势误判多时可调整 trend 参数"
        ),
    }


def optimize_intraday_friction_with_deepseek(
    portfolio_summary: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _section_cfg(settings)
    if not cfg.get("llm_optimize"):
        return {"skipped": True, "reason": "intraday_whatif.llm_optimize disabled"}

    whatif = portfolio_summary.get("intraday_friction_whatif") or {}
    if whatif.get("skipped"):
        return {"skipped": True, "reason": whatif.get("skip_reason") or "intraday friction what-if skipped"}

    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(cfg.get("llm_provider") or "deepseek")
    if not resolve_chat_provider(provider):
        return {"skipped": True, "reason": "no llm provider (set DEEPSEEK_API_KEY)"}

    import json

    payload = build_intraday_friction_optimize_payload(portfolio_summary, settings=settings)
    result = chat_json(
        system=(
            "你是 daily-run harness 盘中摩擦/趋势优化器。输出 JSON："
            '{"friction_min_return_pct":0.005,"trend_min_points":2,"trend_delta_threshold":1.0,'
            '"rationale":"中文理由","confidence":0.0-1.0}。'
            "规则：1) 在 constraints 内；2) friction_would_pass 多时可略降 friction_min_return_pct；"
            "3) trend_mismatch 多时可降低 trend_delta_threshold 或提高 trend_min_points；"
            "4) 纪律良好时可维持或略收紧 friction；5) rationale 一句话。"
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

    ratios = _clamp_values(result, _FRICTION_BOUNDS)
    if len(ratios) < 3:
        return {"skipped": True, "reason": "llm ratios incomplete", "raw": result}

    rationale = str(result.get("rationale") or "").strip()
    policy_line = format_intraday_friction_policy_line(ratios, rationale=rationale)
    evidence = {
        "memory": [
            (
                f"DeepSeek 摩擦趋势最优：friction={ratios['friction_min_return_pct']:.4f} "
                f"trend_pts={ratios['trend_min_points']:.0f} "
                f"trend_delta={ratios['trend_delta_threshold']:.1f}"
            )
        ],
        "policy": [policy_line] if policy_line else [],
        "playbook": ["DeepSeek 摩擦趋势最优解已写入 harness policy"],
        "plan": ["intraday：验证 friction/trend 参数与落账成交对齐"],
        "summary": f"intraday_friction_llm friction={ratios['friction_min_return_pct']:.4f}",
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


def apply_intraday_friction_llm_optimal_to_flat(
    merged: dict[str, float],
    state: Any,
    *,
    settings: dict[str, Any],
) -> bool:
    from agent_reach.daily_run.harness_policy import evolution_mode

    optimal = _find_parsed_in_state(state, settings=settings)
    if not optimal:
        return False
    applied = False
    if "friction_min_return_pct" in optimal and (
        evolution_mode(settings, "friction_min_return_pct") == "harness"
        or "friction_min_return_pct" in merged
    ):
        merged["friction_min_return_pct"] = optimal["friction_min_return_pct"]
        applied = True
    return applied


def apply_intraday_friction_llm_optimal_to_trend(
    merged: dict[str, Any],
    state: Any,
    *,
    settings: dict[str, Any],
) -> bool:
    from agent_reach.daily_run.harness_policy import evolution_mode

    optimal = _find_parsed_in_state(state, settings=settings)
    if not optimal:
        return False
    applied = False
    for key in ("trend_min_points", "trend_delta_threshold"):
        if key in optimal and evolution_mode(settings, key) == "harness":
            merged[key] = optimal[key]
            applied = True
    return applied

# -*- coding: utf-8
"""DeepSeek optimizer for harness commission / slippage (friction model)."""

from __future__ import annotations

import re
from typing import Any, Optional

from agent_reach.daily_run.harness_policy import (
    friction_commission_rate_default,
    friction_slippage_rate_default,
)

_MODEL_PREFIX = "what-if DeepSeek 摩擦模型最优"
_MODEL_RE = re.compile(
    r"what-if DeepSeek 摩擦模型最优：commission_rate=([\d.]+)\s+slippage_rate=([\d.]+)",
    re.IGNORECASE,
)

_MODEL_BOUNDS = {
    "commission_rate": (0.0005, 0.003),
    "slippage_rate": (0.0005, 0.003),
}


def _section_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    root = dict((settings or {}).get("harness_evolution") or {})
    sec = dict((settings or {}).get("friction_model") or {})
    intraday_cfg = dict((settings or {}).get("intraday_whatif") or {})
    llm_refine = dict((settings or {}).get("harness") or {}).get("llm_refine") or {}
    if root.get("llm_optimize") is False or sec.get("llm_optimize") is False:
        return {"llm_optimize": False}
    provider = str(
        sec.get("llm_provider")
        or intraday_cfg.get("llm_provider")
        or root.get("llm_provider")
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
        out[key] = round(max(lo, min(hi, float(val))), 4)
    return out


def format_friction_model_policy_line(ratios: dict[str, float], *, rationale: str = "") -> str:
    cr = ratios.get("commission_rate")
    sr = ratios.get("slippage_rate")
    if cr is None or sr is None:
        return ""
    line = (
        f"{_MODEL_PREFIX}：commission_rate={float(cr):.4f} "
        f"slippage_rate={float(sr):.4f}"
    )
    reason = str(rationale or "").strip()
    if reason:
        line += f" — {reason[:120]}"
    return line


def parse_friction_model_policy_line(text: str) -> Optional[dict[str, float]]:
    match = _MODEL_RE.search(str(text or ""))
    if not match:
        return None
    return _clamp_values(
        {"commission_rate": float(match.group(1)), "slippage_rate": float(match.group(2))},
        _MODEL_BOUNDS,
    )


def _find_parsed_in_state(state: Any, *, settings: dict[str, Any]) -> Optional[dict[str, float]]:
    from agent_reach.daily_run.harness_policy import _collect_text_blobs, _overlay_sources

    for blob in _collect_text_blobs(
        state, sources=_overlay_sources(settings), kind="policy", settings=settings
    ):
        parsed = parse_friction_model_policy_line(blob)
        if parsed:
            return parsed
    return None


def build_friction_model_payload(
    portfolio_summary: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = settings or {}
    friction = portfolio_summary.get("intraday_friction_whatif") or {}
    return {
        "as_of": portfolio_summary.get("as_of"),
        "friction_whatif": {
            "friction_blocked_actual": friction.get("friction_blocked_actual"),
            "friction_would_pass": friction.get("friction_would_pass"),
            "trend_mismatch": friction.get("trend_mismatch"),
        },
        "current": {
            "commission_rate": friction_commission_rate_default(cfg),
            "slippage_rate": friction_slippage_rate_default(cfg),
        },
        "constraints": {k: list(v) for k, v in _MODEL_BOUNDS.items()},
        "objective": (
            "根据盘中摩擦 what-if，给出 commission_rate / slippage_rate 最优解；"
            "摩擦阻断偏多时可略降费率假设，纪律良好时可维持或略收紧"
        ),
    }


def optimize_friction_model_with_deepseek(
    portfolio_summary: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _section_cfg(settings)
    if not cfg.get("llm_optimize"):
        return {"skipped": True, "reason": "friction_model.llm_optimize disabled"}

    friction = portfolio_summary.get("intraday_friction_whatif") or {}
    if friction.get("skipped"):
        return {"skipped": True, "reason": "intraday friction what-if skipped"}

    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(cfg.get("llm_provider") or "deepseek")
    if not resolve_chat_provider(provider):
        return {"skipped": True, "reason": "no llm provider (set DEEPSEEK_API_KEY)"}

    import json

    payload = build_friction_model_payload(portfolio_summary, settings=settings)
    result = chat_json(
        system=(
            "你是 daily-run harness 摩擦模型优化器。输出 JSON："
            '{"commission_rate":0.0015,"slippage_rate":0.001,'
            '"rationale":"中文理由","confidence":0.0-1.0}。'
            "规则：1) 在 constraints 内；2) friction_would_pass 多时可略降 commission/slippage；"
            "3) 阻断合理时可维持或略升；4) rationale 一句话。"
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

    ratios = _clamp_values(result, _MODEL_BOUNDS)
    if len(ratios) < 2:
        return {"skipped": True, "reason": "llm ratios incomplete", "raw": result}

    rationale = str(result.get("rationale") or "").strip()
    policy_line = format_friction_model_policy_line(ratios, rationale=rationale)
    evidence = {
        "memory": [
            f"DeepSeek 摩擦模型最优：commission={ratios['commission_rate']:.4f} "
            f"slippage={ratios['slippage_rate']:.4f}"
        ],
        "policy": [policy_line] if policy_line else [],
        "playbook": ["DeepSeek 摩擦模型最优解已写入 harness policy"],
        "plan": ["intraday：验证 commission/slippage 与摩擦阻断统计对齐"],
        "summary": f"friction_model_llm commission={ratios['commission_rate']:.4f}",
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


def apply_friction_model_llm_optimal_to_policy(
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
    for key in ("commission_rate", "slippage_rate"):
        if key in optimal and evolution_mode(settings, key) == "harness":
            merged[key] = optimal[key]
            applied = True
    return applied

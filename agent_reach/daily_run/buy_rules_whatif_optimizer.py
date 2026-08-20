# -*- coding: utf-8
"""DeepSeek / LLM optimizer for harness buy sizing from what-if notional comparison."""

from __future__ import annotations

import re
from typing import Any, Optional

from agent_reach.daily_run.harness_policy import _position_policy

_LLM_BUY_OPTIMAL_PREFIX = "what-if DeepSeek 买入最优"
_LLM_BUY_OPTIMAL_RE = re.compile(
    r"what-if DeepSeek 买入最优：deploy_ratio=([\d.]+)\s+max_position_pct=([\d.]+)",
    re.IGNORECASE,
)

_BUY_BOUNDS = {
    "deploy_ratio": (0.05, 1.0),
    "max_position_pct": (5.0, 50.0),
}


def whatif_buy_optimize_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    cfg = dict((settings or {}).get("buy_rules_whatif") or {})
    sell_cfg = dict((settings or {}).get("sell_rules_whatif") or {})
    llm_refine = dict((settings or {}).get("harness") or {}).get("llm_refine") or {}
    if cfg.get("llm_optimize") is False:
        return {"llm_optimize": False}
    provider = str(
        cfg.get("llm_provider")
        or sell_cfg.get("llm_provider")
        or llm_refine.get("provider")
        or "deepseek"
    )
    return {
        "llm_optimize": cfg.get("llm_optimize", sell_cfg.get("llm_optimize", True)),
        "llm_provider": provider,
        "llm_model": cfg.get("llm_model") or sell_cfg.get("llm_model") or llm_refine.get("model"),
        "llm_timeout_seconds": int(
            cfg.get("llm_timeout_seconds")
            or sell_cfg.get("llm_timeout_seconds")
            or llm_refine.get("timeout_seconds")
            or 45
        ),
        "llm_temperature": float(
            cfg.get("llm_temperature") or sell_cfg.get("llm_temperature") or 0.1
        ),
    }


def clamp_buy_optimal(raw: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, (lo, hi) in _BUY_BOUNDS.items():
        val = raw.get(key)
        if val is None:
            continue
        out[key] = round(max(lo, min(hi, float(val))), 3)
    return out


def format_buy_llm_optimal_policy_line(ratios: dict[str, float], *, rationale: str = "") -> str:
    deploy = ratios.get("deploy_ratio")
    max_pct = ratios.get("max_position_pct")
    if deploy is None or max_pct is None:
        return ""
    line = (
        f"{_LLM_BUY_OPTIMAL_PREFIX}：deploy_ratio={float(deploy):.2f} "
        f"max_position_pct={float(max_pct):.2f}"
    )
    reason = str(rationale or "").strip()
    if reason:
        line += f" — {reason[:120]}"
    return line


def parse_buy_llm_optimal_policy_line(text: str) -> Optional[dict[str, float]]:
    match = _LLM_BUY_OPTIMAL_RE.search(str(text or ""))
    if not match:
        return None
    return clamp_buy_optimal(
        {
            "deploy_ratio": float(match.group(1)),
            "max_position_pct": float(match.group(2)),
        }
    )


def find_buy_llm_optimal_in_state(state: Any, *, settings: dict[str, Any]) -> Optional[dict[str, float]]:
    from agent_reach.daily_run.harness_policy import _collect_text_blobs, _overlay_sources

    sources = _overlay_sources(settings)
    for blob in _collect_text_blobs(state, sources=sources, kind="policy", settings=settings):
        parsed = parse_buy_llm_optimal_policy_line(blob)
        if parsed:
            return parsed
    return None


def build_buy_whatif_optimize_payload(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    whatif = report.get("buy_rules_whatif") or {}
    sell_whatif = report.get("sell_rules_whatif") or {}
    policy = _position_policy(settings or {})
    rows = []
    for row in whatif.get("rows") or []:
        rows.append(
            {
                "code": row.get("code"),
                "name": row.get("name"),
                "baseline_bought": row.get("actual_bought"),
                "evolved_bought": row.get("hypothetical_bought"),
                "share_delta": row.get("share_delta"),
                "block_reason": row.get("block_reason"),
            }
        )
    return {
        "week_start": report.get("week_start"),
        "week_end": report.get("week_end"),
        "weekly_pnl": report.get("weekly_pnl"),
        "weekly_pnl_pct": report.get("weekly_pnl_pct"),
        "whatif": {
            "baseline_buy_notional": whatif.get("actual_buy_notional"),
            "evolved_buy_notional": whatif.get("hypothetical_buy_notional"),
            "buy_notional_delta": whatif.get("buy_notional_delta"),
            "rows": rows,
        },
        "sell_whatif_summary": {
            "realized_pnl_delta": sell_whatif.get("realized_pnl_delta"),
            "skipped": sell_whatif.get("skipped"),
        },
        "current_buy_policy": {
            "deploy_ratio": policy.get("deploy_ratio"),
            "max_position_pct": policy.get("max_position_pct"),
        },
        "constraints": {
            "deploy_ratio": list(_BUY_BOUNDS["deploy_ratio"]),
            "max_position_pct": list(_BUY_BOUNDS["max_position_pct"]),
        },
        "objective": (
            "根据买入 what-if 基准 vs 自进化成交额/股数对比与周度净值，"
            "给出下一周 harness deploy_ratio / max_position_pct 最优解"
        ),
    }


def optimize_buy_rules_whatif_with_deepseek(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Call DeepSeek to propose optimal deploy_ratio / max_position_pct for harness evolution."""
    cfg = whatif_buy_optimize_cfg(settings)
    if not cfg.get("llm_optimize"):
        return {"skipped": True, "reason": "buy_rules_whatif.llm_optimize disabled"}

    whatif = report.get("buy_rules_whatif") or {}
    if whatif.get("skipped"):
        return {"skipped": True, "reason": "buy what-if skipped"}

    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(cfg.get("llm_provider") or "deepseek")
    if not resolve_chat_provider(provider):
        return {"skipped": True, "reason": "no llm provider (set DEEPSEEK_API_KEY)"}

    import json

    payload = build_buy_whatif_optimize_payload(report, settings=settings)
    result = chat_json(
        system=(
            "你是 A 股量化 daily-run harness 买入 sizing 优化器。"
            "根据买入 what-if 基准 vs 自进化成交额对比，输出 JSON："
            '{"deploy_ratio":0.55,"max_position_pct":28,"rationale":"中文理由","confidence":0.0-1.0}。'
            "规则：1) deploy_ratio 与 max_position_pct 必须在 constraints 范围内；"
            "2) 基准买入成交额显著高于自进化（更激进）且周度净值承压时，收紧 deploy/max_position；"
            "3) 基准买入更优（错过机会少）时可适度上调 deploy_ratio 或 max_position_pct；"
            "4) 自进化买入更优时维持或略收紧；"
            "5) 可参考 sell_whatif_summary 的 realized_pnl_delta 综合权衡；"
            "6) rationale 一句话说明权衡。"
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

    ratios = clamp_buy_optimal(result)
    if not ratios or len(ratios) < 2:
        return {"skipped": True, "reason": "llm ratios incomplete", "raw": result}

    rationale = str(result.get("rationale") or "").strip()
    confidence = result.get("confidence")
    policy_line = format_buy_llm_optimal_policy_line(ratios, rationale=rationale)

    memory = [
        (
            f"DeepSeek 买入 what-if 最优：deploy={ratios['deploy_ratio']:.0%} "
            f"max_pos={ratios['max_position_pct']:.0f}%"
        ),
    ]
    if confidence is not None:
        memory.append(f"DeepSeek 买入置信度 {float(confidence):.2f}")

    evidence = {
        "memory": memory,
        "policy": [policy_line] if policy_line else [],
        "playbook": [
            "买入 what-if DeepSeek 最优解已写入 harness policy，runtime 直接采用 LLM deploy 参数"
        ],
        "plan": ["weekly：验证 DeepSeek 最优 deploy_ratio 与下一周 intraday 买入 sizing 对齐"],
        "summary": (
            f"whatif_buy_llm deploy={ratios['deploy_ratio']:.2f} "
            f"max_pos={ratios['max_position_pct']:.1f}"
        ),
        "llm_optimal": {**ratios, "rationale": rationale, "confidence": confidence},
    }
    return {
        "skipped": False,
        "planner": "deepseek",
        "provider": provider,
        "optimal": ratios,
        "evidence": evidence,
        "raw": result,
    }


def apply_whatif_buy_llm_optimal_to_policy(
    merged: dict[str, float],
    state: Any,
    *,
    settings: dict[str, Any],
) -> bool:
    """When DeepSeek buy optimal policy exists, set merged position policy directly."""
    from agent_reach.daily_run.harness_policy import evolution_mode

    optimal = find_buy_llm_optimal_in_state(state, settings=settings)
    if not optimal:
        return False
    if evolution_mode(settings, "deploy_ratio") == "harness" and "deploy_ratio" in optimal:
        merged["deploy_ratio"] = optimal["deploy_ratio"]
    if evolution_mode(settings, "max_position_pct") == "harness" and "max_position_pct" in optimal:
        merged["max_position_pct"] = optimal["max_position_pct"]
    return True

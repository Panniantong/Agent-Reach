# -*- coding: utf-8
"""DeepSeek / LLM optimizer for harness sell-ratio evolution from what-if PnL."""

from __future__ import annotations

import re
from typing import Any, Optional

from agent_reach.daily_run.portfolio_manager import deep_loss_policy

_LLM_OPTIMAL_PREFIX = "what-if DeepSeek 最优"
_LLM_OPTIMAL_RE = re.compile(
    r"what-if DeepSeek 最优：sell_ratio=([\d.]+)\s+non_deep_loss_sell_ratio=([\d.]+)\s+cover_ratio=([\d.]+)",
    re.IGNORECASE,
)

_RATIO_BOUNDS = {
    "sell_ratio": (0.1, 1.0),
    "non_deep_loss_sell_ratio": (0.1, 1.0),
    "cover_ratio": (0.8, 1.5),
}


def whatif_optimize_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    cfg = dict((settings or {}).get("sell_rules_whatif") or {})
    llm_refine = dict((settings or {}).get("harness") or {}).get("llm_refine") or {}
    if cfg.get("llm_optimize") is False:
        return {"llm_optimize": False}
    provider = str(cfg.get("llm_provider") or llm_refine.get("provider") or "deepseek")
    return {
        "llm_optimize": cfg.get("llm_optimize", True),
        "llm_provider": provider,
        "llm_model": cfg.get("llm_model") or llm_refine.get("model"),
        "llm_timeout_seconds": int(cfg.get("llm_timeout_seconds") or llm_refine.get("timeout_seconds") or 45),
        "llm_temperature": float(cfg.get("llm_temperature") or 0.1),
    }


def clamp_optimal_ratios(raw: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, (lo, hi) in _RATIO_BOUNDS.items():
        val = raw.get(key)
        if val is None:
            continue
        out[key] = round(max(lo, min(hi, float(val))), 3)
    return out


def format_llm_optimal_policy_line(ratios: dict[str, float], *, rationale: str = "") -> str:
    sr = ratios.get("sell_ratio")
    nd = ratios.get("non_deep_loss_sell_ratio")
    cr = ratios.get("cover_ratio")
    if sr is None or nd is None or cr is None:
        return ""
    line = (
        f"{_LLM_OPTIMAL_PREFIX}：sell_ratio={float(sr):.2f} "
        f"non_deep_loss_sell_ratio={float(nd):.2f} cover_ratio={float(cr):.2f}"
    )
    reason = str(rationale or "").strip()
    if reason:
        line += f" — {reason[:120]}"
    return line


def parse_llm_optimal_policy_line(text: str) -> Optional[dict[str, float]]:
    match = _LLM_OPTIMAL_RE.search(str(text or ""))
    if not match:
        return None
    return clamp_optimal_ratios(
        {
            "sell_ratio": float(match.group(1)),
            "non_deep_loss_sell_ratio": float(match.group(2)),
            "cover_ratio": float(match.group(3)),
        }
    )


def find_llm_optimal_ratios_in_state(state: Any, *, settings: dict[str, Any]) -> Optional[dict[str, float]]:
    from agent_reach.daily_run.harness_policy import _collect_text_blobs, _overlay_sources

    sources = _overlay_sources(settings)
    for blob in _collect_text_blobs(state, sources=sources, kind="policy", settings=settings):
        parsed = parse_llm_optimal_policy_line(blob)
        if parsed:
            return parsed
    return None


def build_whatif_optimize_payload(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    whatif = report.get("sell_rules_whatif") or {}
    policy = deep_loss_policy(settings or {})
    rows = []
    for row in whatif.get("rows") or []:
        rows.append(
            {
                "code": row.get("code"),
                "name": row.get("name"),
                "baseline_sold": row.get("actual_sold"),
                "evolved_sold": row.get("hypothetical_sold"),
                "share_delta": row.get("share_delta"),
                "is_deep_loss": row.get("is_deep_loss"),
                "block_reason": row.get("block_reason"),
            }
        )
    return {
        "week_start": report.get("week_start"),
        "week_end": report.get("week_end"),
        "weekly_pnl": report.get("weekly_pnl"),
        "weekly_pnl_pct": report.get("weekly_pnl_pct"),
        "whatif": {
            "baseline_realized_pnl": whatif.get("actual_realized_pnl"),
            "evolved_realized_pnl": whatif.get("hypothetical_realized_pnl"),
            "realized_pnl_delta": whatif.get("realized_pnl_delta"),
            "rows": rows,
        },
        "current_ratios": {
            "sell_ratio": policy.get("sell_ratio"),
            "non_deep_loss_sell_ratio": policy.get("non_deep_loss_sell_ratio"),
            "cover_ratio": policy.get("cover_ratio"),
        },
        "constraints": {
            "sell_ratio": list(_RATIO_BOUNDS["sell_ratio"]),
            "non_deep_loss_sell_ratio": list(_RATIO_BOUNDS["non_deep_loss_sell_ratio"]),
            "cover_ratio": list(_RATIO_BOUNDS["cover_ratio"]),
            "full_clear_when": (
                "基准已实现显著高于自进化（realized_pnl_delta<=-500 或存在基准超额卖出），"
                "且周度 defensive 语境下可建议 sell_ratio=1.0 全清"
            ),
        },
        "objective": (
            "根据基准 vs 自进化 what-if 已实现盈亏与周度净值，"
            "给出下一周 harness 卖出比例最优解；"
            "默认 partial sell，满足 full_clear_when 条件允许时可输出 1.0 全清"
        ),
    }


def optimize_sell_rules_whatif_with_deepseek(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Call DeepSeek to propose optimal sell_ratio / cover_ratio for harness evolution."""
    cfg = whatif_optimize_cfg(settings)
    if not cfg.get("llm_optimize"):
        return {"skipped": True, "reason": "sell_rules_whatif.llm_optimize disabled"}

    whatif = report.get("sell_rules_whatif") or {}
    if whatif.get("skipped"):
        return {"skipped": True, "reason": "what-if skipped"}

    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(cfg.get("llm_provider") or "deepseek")
    if not resolve_chat_provider(provider):
        return {"skipped": True, "reason": "no llm provider (set DEEPSEEK_API_KEY)"}

    import json

    payload = build_whatif_optimize_payload(report, settings=settings)
    result = chat_json(
        system=(
            "你是 A 股量化 daily-run harness 卖出比例优化器。"
            "根据 what-if 基准 vs 自进化盈亏对比，输出 JSON："
            '{"sell_ratio":0.55,"non_deep_loss_sell_ratio":0.68,"cover_ratio":1.05,'
            '"rationale":"中文理由","confidence":0.0-1.0}。'
            "规则：1) sell_ratio 与 non_deep_loss_sell_ratio 必须在 constraints 范围内；"
            "2) 默认 partial sell；仅当 full_clear_when 条件满足时可建议 1.0 全清；"
            "3) 基准已实现显著更高时可上调比例，条件充分时可至 1.0；"
            "4) 自进化已实现更优时维持或略收紧 partial sell；"
            "5) rationale 一句话说明权衡。"
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

    ratios = clamp_optimal_ratios(result)
    if not ratios or len(ratios) < 3:
        return {"skipped": True, "reason": "llm ratios incomplete", "raw": result}

    rationale = str(result.get("rationale") or "").strip()
    confidence = result.get("confidence")
    policy_line = format_llm_optimal_policy_line(ratios, rationale=rationale)

    memory = [
        (
            f"DeepSeek what-if 最优：sell_ratio={ratios['sell_ratio']:.0%} "
            f"non_deep={ratios['non_deep_loss_sell_ratio']:.0%} "
            f"cover={ratios['cover_ratio']:.0%}"
        ),
    ]
    if confidence is not None:
        memory.append(f"DeepSeek 置信度 {float(confidence):.2f}")

    evidence = {
        "memory": memory,
        "policy": [policy_line] if policy_line else [],
        "playbook": [
            "what-if DeepSeek 最优解已写入 harness policy，runtime 直接采用 LLM 比例（条件允许时可全清）"
        ],
        "plan": ["weekly：验证 DeepSeek 最优 sell_ratio 与下一周 defensive_trim 成交对齐"],
        "summary": (
            f"whatif_llm sr={ratios['sell_ratio']:.2f} "
            f"nd={ratios['non_deep_loss_sell_ratio']:.2f} "
            f"cr={ratios['cover_ratio']:.2f}"
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


def apply_whatif_llm_optimal_to_policy(
    merged: dict[str, float],
    state: Any,
    *,
    settings: dict[str, Any],
) -> bool:
    """When DeepSeek optimal policy exists, set merged ratios directly (within clamps)."""
    from agent_reach.daily_run.harness_policy import evolution_mode

    optimal = find_llm_optimal_ratios_in_state(state, settings=settings)
    if not optimal:
        return False
    if evolution_mode(settings, "sell_ratio") == "harness" and "sell_ratio" in optimal:
        merged["sell_ratio"] = optimal["sell_ratio"]
    if evolution_mode(settings, "non_deep_loss_sell_ratio") == "harness" and "non_deep_loss_sell_ratio" in optimal:
        merged["non_deep_loss_sell_ratio"] = optimal["non_deep_loss_sell_ratio"]
    if "cover_ratio" in optimal:
        merged["cover_ratio"] = optimal["cover_ratio"]
    return True

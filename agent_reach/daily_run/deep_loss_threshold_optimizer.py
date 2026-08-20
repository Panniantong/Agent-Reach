# -*- coding: utf-8
"""DeepSeek optimizer for deep-loss threshold harness evolution."""

from __future__ import annotations

import re
from typing import Any, Optional

from agent_reach.daily_run.harness_policy import deep_loss_policy_default

_THRESHOLD_PREFIX = "what-if DeepSeek 深亏阈值最优"
_THRESHOLD_RE = re.compile(
    r"what-if DeepSeek 深亏阈值最优：loss_cny_threshold=([\d.]+)\s+"
    r"loss_pct_threshold=([\d.]+)\s+deep_loss_tier_multiplier=([\d.]+)",
    re.IGNORECASE,
)

_THRESHOLD_BOUNDS = {
    "loss_cny_threshold": (1000.0, 10000.0),
    "loss_pct_threshold": (5.0, 50.0),
    "deep_loss_tier_multiplier": (1.2, 4.0),
}


def _section_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    root = dict((settings or {}).get("harness_evolution") or {})
    sec = dict((settings or {}).get("deep_loss_threshold") or {})
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


def format_deep_loss_threshold_policy_line(ratios: dict[str, float], *, rationale: str = "") -> str:
    lc = ratios.get("loss_cny_threshold")
    lp = ratios.get("loss_pct_threshold")
    tm = ratios.get("deep_loss_tier_multiplier")
    if lc is None or lp is None or tm is None:
        return ""
    line = (
        f"{_THRESHOLD_PREFIX}：loss_cny_threshold={float(lc):.0f} "
        f"loss_pct_threshold={float(lp):.1f} deep_loss_tier_multiplier={float(tm):.2f}"
    )
    reason = str(rationale or "").strip()
    if reason:
        line += f" — {reason[:120]}"
    return line


def parse_deep_loss_threshold_policy_line(text: str) -> Optional[dict[str, float]]:
    match = _THRESHOLD_RE.search(str(text or ""))
    if not match:
        return None
    return _clamp_values(
        {
            "loss_cny_threshold": float(match.group(1)),
            "loss_pct_threshold": float(match.group(2)),
            "deep_loss_tier_multiplier": float(match.group(3)),
        },
        _THRESHOLD_BOUNDS,
    )


def _find_parsed_in_state(state: Any, *, settings: dict[str, Any]) -> Optional[dict[str, float]]:
    from agent_reach.daily_run.harness_policy import _collect_text_blobs, _overlay_sources

    for blob in _collect_text_blobs(
        state, sources=_overlay_sources(settings), kind="policy", settings=settings
    ):
        parsed = parse_deep_loss_threshold_policy_line(blob)
        if parsed:
            return parsed
    return None


def build_deep_loss_threshold_payload(
    portfolio_summary: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = settings or {}
    sell_whatif = portfolio_summary.get("sell_rules_whatif") or {}
    deep_rows = []
    for row in sell_whatif.get("rows") or []:
        if not row.get("is_deep_loss"):
            continue
        deep_rows.append(
            {
                "code": row.get("code"),
                "name": row.get("name"),
                "actual_sold": row.get("actual_sold"),
                "hypothetical_sold": row.get("hypothetical_sold"),
                "share_delta": row.get("share_delta"),
                "block_reason": row.get("block_reason"),
            }
        )
    return {
        "as_of": portfolio_summary.get("as_of"),
        "daily_pnl": portfolio_summary.get("daily_pnl"),
        "daily_pnl_pct": portfolio_summary.get("daily_pnl_pct"),
        "sell_whatif": {
            "realized_pnl_delta": sell_whatif.get("realized_pnl_delta"),
            "deep_loss_rows": deep_rows[:8],
            "deep_loss_count": len(deep_rows),
        },
        "current": {
            "loss_cny_threshold": deep_loss_policy_default(cfg, "loss_cny_threshold"),
            "loss_pct_threshold": deep_loss_policy_default(cfg, "loss_pct_threshold"),
            "deep_loss_tier_multiplier": deep_loss_policy_default(cfg, "deep_loss_tier_multiplier"),
        },
        "constraints": {k: list(v) for k, v in _THRESHOLD_BOUNDS.items()},
        "objective": (
            "根据深亏持仓与卖出 what-if，给出 loss_cny_threshold / loss_pct_threshold / "
            "deep_loss_tier_multiplier 最优解；深亏处置偏慢时可略降阈值，误杀时可略抬高"
        ),
    }


def optimize_deep_loss_threshold_with_deepseek(
    portfolio_summary: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _section_cfg(settings)
    if not cfg.get("llm_optimize"):
        return {"skipped": True, "reason": "deep_loss_threshold.llm_optimize disabled"}

    sell_whatif = portfolio_summary.get("sell_rules_whatif") or {}
    if sell_whatif.get("skipped"):
        return {"skipped": True, "reason": "sell what-if skipped"}

    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(cfg.get("llm_provider") or "deepseek")
    if not resolve_chat_provider(provider):
        return {"skipped": True, "reason": "no llm provider (set DEEPSEEK_API_KEY)"}

    import json

    payload = build_deep_loss_threshold_payload(portfolio_summary, settings=settings)
    result = chat_json(
        system=(
            "你是 daily-run harness 深亏阈值优化器。输出 JSON："
            '{"loss_cny_threshold":4500,"loss_pct_threshold":8,"deep_loss_tier_multiplier":2.2,'
            '"rationale":"中文理由","confidence":0.0-1.0}。'
            "规则：1) 在 constraints 内；2) 深亏处置滞后时可略降 loss 阈值；"
            "3) 误触发深亏时可略抬高；4) tier_multiplier 与 tier 扩展一致；5) rationale 一句话。"
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

    rationale = str(result.get("rationale") or "").strip()
    policy_line = format_deep_loss_threshold_policy_line(ratios, rationale=rationale)
    evidence = {
        "memory": [
            (
                f"DeepSeek 深亏阈值最优：cny={ratios['loss_cny_threshold']:.0f} "
                f"pct={ratios['loss_pct_threshold']:.1f}% "
                f"tier={ratios['deep_loss_tier_multiplier']:.2f}x"
            )
        ],
        "policy": [policy_line] if policy_line else [],
        "playbook": ["DeepSeek 深亏阈值最优解已写入 harness policy"],
        "plan": ["close：验证深亏 tier 与 defensive_trim 成交对齐"],
        "summary": f"deep_loss_threshold_llm cny={ratios['loss_cny_threshold']:.0f}",
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


def apply_deep_loss_threshold_llm_optimal_to_policy(
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
    for key in ("loss_cny_threshold", "loss_pct_threshold", "deep_loss_tier_multiplier"):
        if key in optimal and evolution_mode(settings, key) == "harness":
            merged[key] = optimal[key]
            applied = True
    return applied

# -*- coding: utf-8
"""DeepSeek optimizer for intraday sell scan replay harness evolution."""

from __future__ import annotations

import re
from typing import Any, Optional

from agent_reach.daily_run.harness_policy import macro_veto_default
from agent_reach.daily_run.portfolio_manager import deep_loss_policy

_SELL_SCAN_PREFIX = "what-if DeepSeek 卖出scan最优"
_SELL_SCAN_RE = re.compile(
    r"what-if DeepSeek 卖出scan最优：sell_ratio=([\d.]+)\s+"
    r"non_deep_loss_sell_ratio=([\d.]+)\s+macro_veto=([\d.]+)",
    re.IGNORECASE,
)

_SELL_SCAN_BOUNDS = {
    "sell_ratio": (0.1, 1.0),
    "non_deep_loss_sell_ratio": (0.1, 1.0),
    "macro_veto": (25.0, 50.0),
}


def _section_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    root = dict((settings or {}).get("harness_evolution") or {})
    sec = dict((settings or {}).get("intraday_sell_whatif") or {})
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


def format_intraday_sell_policy_line(ratios: dict[str, float], *, rationale: str = "") -> str:
    sr = ratios.get("sell_ratio")
    nd = ratios.get("non_deep_loss_sell_ratio")
    mv = ratios.get("macro_veto")
    if sr is None or nd is None or mv is None:
        return ""
    line = (
        f"{_SELL_SCAN_PREFIX}：sell_ratio={float(sr):.2f} "
        f"non_deep_loss_sell_ratio={float(nd):.2f} macro_veto={float(mv):.2f}"
    )
    reason = str(rationale or "").strip()
    if reason:
        line += f" — {reason[:120]}"
    return line


def parse_intraday_sell_policy_line(text: str) -> Optional[dict[str, float]]:
    match = _SELL_SCAN_RE.search(str(text or ""))
    if not match:
        return None
    return _clamp_values(
        {
            "sell_ratio": float(match.group(1)),
            "non_deep_loss_sell_ratio": float(match.group(2)),
            "macro_veto": float(match.group(3)),
        },
        _SELL_SCAN_BOUNDS,
    )


def _find_parsed_in_state(state: Any, *, settings: dict[str, Any]) -> Optional[dict[str, float]]:
    from agent_reach.daily_run.harness_policy import _collect_text_blobs, _overlay_sources

    for blob in _collect_text_blobs(
        state, sources=_overlay_sources(settings), kind="policy", settings=settings
    ):
        parsed = parse_intraday_sell_policy_line(blob)
        if parsed:
            return parsed
    return None


def _whatif_block(source: dict[str, Any]) -> dict[str, Any]:
    return dict(source.get("intraday_sell_whatif") or {})


def build_intraday_sell_optimize_payload(
    source: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = settings or {}
    whatif = _whatif_block(source)
    policy = deep_loss_policy(cfg)
    return {
        "as_of": source.get("as_of") or source.get("week_end"),
        "week_start": source.get("week_start"),
        "week_end": source.get("week_end"),
        "weekly_pnl": source.get("weekly_pnl"),
        "daily_pnl": source.get("daily_pnl"),
        "whatif": {
            "missed_sell_signals": whatif.get("missed_sell_signals"),
            "sell_share_delta": whatif.get("sell_share_delta"),
            "actual_sell_shares": whatif.get("actual_sell_shares"),
            "hypothetical_sell_shares": whatif.get("hypothetical_sell_shares"),
            "rows": (whatif.get("rows") or [])[:8],
        },
        "current": {
            "sell_ratio": policy.get("sell_ratio"),
            "non_deep_loss_sell_ratio": policy.get("non_deep_loss_sell_ratio"),
            "macro_veto": macro_veto_default(cfg),
        },
        "constraints": {k: list(v) for k, v in _SELL_SCAN_BOUNDS.items()},
        "objective": (
            "根据盘中卖出 scan replay，给出 sell_ratio / non_deep_loss_sell_ratio / macro_veto 最优解；"
            "错失卖出信号多时可 step-up 比例或略降 macro_veto 以更早触发宏观避险"
        ),
    }


def optimize_intraday_sell_with_deepseek(
    source: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _section_cfg(settings)
    if not cfg.get("llm_optimize"):
        return {"skipped": True, "reason": "intraday_sell_whatif.llm_optimize disabled"}

    whatif = _whatif_block(source)
    if whatif.get("skipped"):
        return {"skipped": True, "reason": whatif.get("skip_reason") or "intraday sell what-if skipped"}

    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(cfg.get("llm_provider") or "deepseek")
    if not resolve_chat_provider(provider):
        return {"skipped": True, "reason": "no llm provider (set DEEPSEEK_API_KEY)"}

    import json

    payload = build_intraday_sell_optimize_payload(source, settings=settings)
    result = chat_json(
        system=(
            "你是 daily-run harness 盘中卖出 scan 优化器。输出 JSON："
            '{"sell_ratio":0.55,"non_deep_loss_sell_ratio":0.65,"macro_veto":38,'
            '"rationale":"中文理由","confidence":0.0-1.0}。'
            "规则：1) 在 constraints 内；2) missed_sell_signals 多时可上调 sell 比例或略降 macro_veto；"
            "3) 自进化卖出过多时可维持 partial sell 并略抬高 macro_veto；4) rationale 一句话。"
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

    ratios = _clamp_values(result, _SELL_SCAN_BOUNDS)
    if len(ratios) < 3:
        return {"skipped": True, "reason": "llm ratios incomplete", "raw": result}

    rationale = str(result.get("rationale") or "").strip()
    policy_line = format_intraday_sell_policy_line(ratios, rationale=rationale)
    evidence = {
        "memory": [
            (
                f"DeepSeek 卖出scan最优：sell={ratios['sell_ratio']:.0%} "
                f"non_deep={ratios['non_deep_loss_sell_ratio']:.0%} "
                f"macro_veto={ratios['macro_veto']:.0f}"
            )
        ],
        "policy": [policy_line] if policy_line else [],
        "playbook": ["DeepSeek 卖出 scan 最优解已写入 harness policy"],
        "plan": ["intraday：验证 sell_ratio / macro_veto 与 scan replay 对齐"],
        "summary": f"intraday_sell_llm sr={ratios['sell_ratio']:.2f} mv={ratios['macro_veto']:.0f}",
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


def apply_intraday_sell_llm_optimal_to_deep_loss(
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
    for key in ("sell_ratio", "non_deep_loss_sell_ratio"):
        if key in optimal and evolution_mode(settings, key) == "harness":
            merged[key] = optimal[key]
            applied = True
    return applied


def apply_intraday_sell_llm_optimal_to_flat(
    merged: dict[str, float],
    state: Any,
    *,
    settings: dict[str, Any],
) -> bool:
    from agent_reach.daily_run.harness_policy import evolution_mode

    optimal = _find_parsed_in_state(state, settings=settings)
    if not optimal or "macro_veto" not in optimal:
        return False
    if evolution_mode(settings, "macro_veto") != "harness":
        return False
    merged["macro_veto"] = optimal["macro_veto"]
    return True

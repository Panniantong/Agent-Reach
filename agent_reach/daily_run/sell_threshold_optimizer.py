# -*- coding: utf-8
"""DeepSeek optimizer for sell-side macro/aggressive thresholds from weekly what-if."""

from __future__ import annotations

import re
from typing import Any, Optional

from agent_reach.daily_run.harness_policy import aggressive_entry_default, macro_veto_default

_SELL_THRESHOLD_PREFIX = "what-if DeepSeek 卖出阈值最优"
_SELL_THRESHOLD_RE = re.compile(
    r"what-if DeepSeek 卖出阈值最优：macro_veto=([\d.]+)\s+aggressive_entry=([\d.]+)",
    re.IGNORECASE,
)

_SELL_THRESHOLD_BOUNDS = {
    "macro_veto": (25.0, 50.0),
    "aggressive_entry": (40.0, 60.0),
}


def _section_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    root = dict((settings or {}).get("harness_evolution") or {})
    sec = dict((settings or {}).get("sell_threshold") or {})
    sell_cfg = dict((settings or {}).get("sell_rules_whatif") or {})
    llm_refine = dict((settings or {}).get("harness") or {}).get("llm_refine") or {}
    if root.get("llm_optimize") is False or sec.get("llm_optimize") is False:
        return {"llm_optimize": False}
    provider = str(
        sec.get("llm_provider")
        or sell_cfg.get("llm_provider")
        or root.get("llm_provider")
        or llm_refine.get("provider")
        or "deepseek"
    )
    return {
        "llm_optimize": sec.get("llm_optimize", sell_cfg.get("llm_optimize", True)),
        "llm_provider": provider,
        "llm_model": sec.get("llm_model") or sell_cfg.get("llm_model") or llm_refine.get("model"),
        "llm_timeout_seconds": int(
            sec.get("llm_timeout_seconds")
            or sell_cfg.get("llm_timeout_seconds")
            or llm_refine.get("timeout_seconds")
            or 45
        ),
        "llm_temperature": float(
            sec.get("llm_temperature") or sell_cfg.get("llm_temperature") or 0.1
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


def format_sell_threshold_policy_line(ratios: dict[str, float], *, rationale: str = "") -> str:
    mv = ratios.get("macro_veto")
    ae = ratios.get("aggressive_entry")
    if mv is None or ae is None:
        return ""
    line = (
        f"{_SELL_THRESHOLD_PREFIX}：macro_veto={float(mv):.2f} "
        f"aggressive_entry={float(ae):.2f}"
    )
    reason = str(rationale or "").strip()
    if reason:
        line += f" — {reason[:120]}"
    return line


def parse_sell_threshold_policy_line(text: str) -> Optional[dict[str, float]]:
    match = _SELL_THRESHOLD_RE.search(str(text or ""))
    if not match:
        return None
    parsed = _clamp_values(
        {"macro_veto": float(match.group(1)), "aggressive_entry": float(match.group(2))},
        _SELL_THRESHOLD_BOUNDS,
    )
    if parsed.get("aggressive_entry", 0) <= parsed.get("macro_veto", 0):
        parsed["aggressive_entry"] = float(parsed["macro_veto"]) + 2.0
    return parsed


def _find_parsed_in_state(state: Any, *, settings: dict[str, Any]) -> Optional[dict[str, float]]:
    from agent_reach.daily_run.harness_policy import _collect_text_blobs, _overlay_sources

    for blob in _collect_text_blobs(
        state, sources=_overlay_sources(settings), kind="policy", settings=settings
    ):
        parsed = parse_sell_threshold_policy_line(blob)
        if parsed:
            return parsed
    return None


def build_sell_threshold_optimize_payload(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = settings or {}
    sell = report.get("sell_rules_whatif") or {}
    intraday_sell = report.get("intraday_sell_whatif") or {}
    return {
        "week_start": report.get("week_start"),
        "week_end": report.get("week_end"),
        "weekly_pnl": report.get("weekly_pnl"),
        "weekly_pnl_pct": report.get("weekly_pnl_pct"),
        "sell_whatif": {
            "realized_pnl_delta": sell.get("realized_pnl_delta"),
            "skipped": sell.get("skipped"),
        },
        "intraday_sell_whatif": {
            "missed_sell_signals": intraday_sell.get("missed_sell_signals"),
            "sell_share_delta": intraday_sell.get("sell_share_delta"),
            "skipped": intraday_sell.get("skipped"),
        },
        "current": {
            "macro_veto": macro_veto_default(cfg),
            "aggressive_entry": aggressive_entry_default(cfg),
        },
        "constraints": {k: list(v) for k, v in _SELL_THRESHOLD_BOUNDS.items()},
        "objective": (
            "根据周度卖出 what-if 与盘中 sell scan replay，给出 macro_veto / aggressive_entry 最优解；"
            "卖晚了或 scan 错失多时可略降 macro_veto；aggressive_entry 必须高于 macro_veto"
        ),
    }


def optimize_sell_threshold_with_deepseek(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _section_cfg(settings)
    if not cfg.get("llm_optimize"):
        return {"skipped": True, "reason": "sell_threshold.llm_optimize disabled"}

    sell = report.get("sell_rules_whatif") or {}
    intraday_sell = report.get("intraday_sell_whatif") or {}
    if sell.get("skipped") and intraday_sell.get("skipped"):
        return {"skipped": True, "reason": "no sell what-if evidence"}

    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(cfg.get("llm_provider") or "deepseek")
    if not resolve_chat_provider(provider):
        return {"skipped": True, "reason": "no llm provider (set DEEPSEEK_API_KEY)"}

    import json

    payload = build_sell_threshold_optimize_payload(report, settings=settings)
    result = chat_json(
        system=(
            "你是 daily-run harness 卖出侧阈值优化器。输出 JSON："
            '{"macro_veto":38,"aggressive_entry":50,"rationale":"中文理由","confidence":0.0-1.0}。'
            "规则：1) 在 constraints 内；2) aggressive_entry > macro_veto；"
            "3) 盘中 scan 错失卖出多时可略降 macro_veto；"
            "4) 周度 defensive 语境可抬高 macro_veto；5) rationale 一句话。"
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

    ratios = _clamp_values(result, _SELL_THRESHOLD_BOUNDS)
    if len(ratios) < 2:
        return {"skipped": True, "reason": "llm ratios incomplete", "raw": result}
    if ratios["aggressive_entry"] <= ratios["macro_veto"]:
        ratios["aggressive_entry"] = ratios["macro_veto"] + 2.0

    rationale = str(result.get("rationale") or "").strip()
    policy_line = format_sell_threshold_policy_line(ratios, rationale=rationale)
    evidence = {
        "memory": [
            (
                f"DeepSeek 卖出阈值最优：macro_veto={ratios['macro_veto']:.0f} "
                f"aggressive_entry={ratios['aggressive_entry']:.0f}"
            )
        ],
        "policy": [policy_line] if policy_line else [],
        "playbook": ["DeepSeek 卖出阈值最优解已写入 harness policy"],
        "plan": ["weekly：验证 macro_veto 与盘中宏观避险卖出对齐"],
        "summary": (
            f"sell_threshold_llm mv={ratios['macro_veto']:.0f} "
            f"ae={ratios['aggressive_entry']:.0f}"
        ),
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


def apply_sell_threshold_llm_optimal_to_flat(
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
    for key in ("macro_veto", "aggressive_entry"):
        if key in optimal and evolution_mode(settings, key) == "harness":
            merged[key] = optimal[key]
            applied = True
    return applied

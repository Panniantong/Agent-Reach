# -*- coding: utf-8
"""DeepSeek optimizer for intraday buy_trends / sell_trends list evolution."""

from __future__ import annotations

import re
from typing import Any, Optional

from agent_reach.daily_run.intraday_policy import _DEFAULT_BUY_TRENDS, _DEFAULT_SELL_TRENDS

_TRENDS_PREFIX = "what-if DeepSeek 趋势集合最优"
_TRENDS_RE = re.compile(
    r"what-if DeepSeek 趋势集合最优：buy_trends=([\w,]+)\s+sell_trends=([\w,]+)",
    re.IGNORECASE,
)

_VALID_TRENDS = frozenset(
    {"rising", "turning_up", "falling", "turning_down", "flat", "mixed"}
)


def _section_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    root = dict((settings or {}).get("harness_evolution") or {})
    sec = dict((settings or {}).get("intraday_trends") or {})
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
        "llm_optimize": sec.get("llm_optimize", intraday_cfg.get("llm_optimize", True)),
        "llm_provider": provider,
        "llm_model": sec.get("llm_model") or intraday_cfg.get("llm_model") or llm_refine.get("model"),
        "llm_timeout_seconds": int(
            sec.get("llm_timeout_seconds")
            or intraday_cfg.get("llm_timeout_seconds")
            or llm_refine.get("timeout_seconds")
            or 45
        ),
        "llm_temperature": float(
            sec.get("llm_temperature") or intraday_cfg.get("llm_temperature") or 0.1
        ),
    }


def _normalize_trend_list(raw: Any, *, fallback: tuple[str, ...]) -> list[str]:
    if isinstance(raw, str):
        items = [part.strip().lower() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, list):
        items = [str(part).strip().lower() for part in raw if str(part).strip()]
    else:
        items = []
    out = [t for t in items if t in _VALID_TRENDS]
    if not out:
        return list(fallback)
    return list(dict.fromkeys(out))


def format_intraday_trends_policy_line(
    trends: dict[str, list[str]],
    *,
    rationale: str = "",
) -> str:
    buy = trends.get("buy_trends") or []
    sell = trends.get("sell_trends") or []
    if not buy or not sell:
        return ""
    line = (
        f"{_TRENDS_PREFIX}：buy_trends={','.join(buy)} "
        f"sell_trends={','.join(sell)}"
    )
    reason = str(rationale or "").strip()
    if reason:
        line += f" — {reason[:120]}"
    return line


def parse_intraday_trends_policy_line(text: str) -> Optional[dict[str, list[str]]]:
    match = _TRENDS_RE.search(str(text or ""))
    if not match:
        return None
    buy = _normalize_trend_list(match.group(1), fallback=_DEFAULT_BUY_TRENDS)
    sell = _normalize_trend_list(match.group(2), fallback=_DEFAULT_SELL_TRENDS)
    return {"buy_trends": buy, "sell_trends": sell}


def _find_parsed_in_state(state: Any, *, settings: dict[str, Any]) -> Optional[dict[str, list[str]]]:
    from agent_reach.daily_run.harness_policy import _collect_text_blobs, _overlay_sources

    for blob in _collect_text_blobs(
        state, sources=_overlay_sources(settings), kind="policy", settings=settings
    ):
        parsed = parse_intraday_trends_policy_line(blob)
        if parsed:
            return parsed
    return None


def build_intraday_trends_optimize_payload(
    source: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = settings or {}
    friction = source.get("intraday_friction_whatif") or {}
    from agent_reach.daily_run.harness_policy import trend_policy_default

    return {
        "as_of": source.get("as_of") or source.get("week_end"),
        "week_start": source.get("week_start"),
        "week_end": source.get("week_end"),
        "whatif": {
            "friction_would_pass": friction.get("friction_would_pass"),
            "trend_mismatch": friction.get("trend_mismatch"),
            "friction_blocked_actual": friction.get("friction_blocked_actual"),
            "rows": (friction.get("rows") or [])[:8],
        },
        "current": {
            "buy_trends": list(
                (cfg.get("intraday") or {}).get("buy_trends") or _DEFAULT_BUY_TRENDS
            ),
            "sell_trends": list(
                (cfg.get("intraday") or {}).get("sell_trends") or _DEFAULT_SELL_TRENDS
            ),
            "trend_min_points": trend_policy_default(cfg, "trend_min_points"),
            "trend_delta_threshold": trend_policy_default(cfg, "trend_delta_threshold"),
        },
        "allowed_trends": sorted(_VALID_TRENDS),
        "objective": (
            "根据盘中摩擦/趋势 what-if，给出 buy_trends / sell_trends 最优集合；"
            "趋势误判多时可收紧 buy_trends；防御性卖出需时可扩展 sell_trends 含 mixed/flat"
        ),
    }


def optimize_intraday_trends_with_deepseek(
    source: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _section_cfg(settings)
    if not cfg.get("llm_optimize"):
        return {"skipped": True, "reason": "intraday_trends.llm_optimize disabled"}

    friction = source.get("intraday_friction_whatif") or {}
    if friction.get("skipped"):
        return {"skipped": True, "reason": friction.get("skip_reason") or "intraday friction what-if skipped"}

    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(cfg.get("llm_provider") or "deepseek")
    if not resolve_chat_provider(provider):
        return {"skipped": True, "reason": "no llm provider (set DEEPSEEK_API_KEY)"}

    import json

    payload = build_intraday_trends_optimize_payload(source, settings=settings)
    result = chat_json(
        system=(
            "你是 daily-run harness 盘中趋势集合优化器。输出 JSON："
            '{"buy_trends":["rising","turning_up"],"sell_trends":["falling","turning_down","mixed"],'
            '"rationale":"中文理由","confidence":0.0-1.0}。'
            "规则：1) 仅使用 allowed_trends 中的值；2) 每侧至少 1 个趋势；"
            "3) trend_mismatch 多时可收紧 buy_trends；4) 防御性卖出语境可扩展 sell_trends；"
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

    trends = {
        "buy_trends": _normalize_trend_list(result.get("buy_trends"), fallback=_DEFAULT_BUY_TRENDS),
        "sell_trends": _normalize_trend_list(result.get("sell_trends"), fallback=_DEFAULT_SELL_TRENDS),
    }
    rationale = str(result.get("rationale") or "").strip()
    policy_line = format_intraday_trends_policy_line(trends, rationale=rationale)
    evidence = {
        "memory": [
            (
                f"DeepSeek 趋势集合最优：buy={','.join(trends['buy_trends'])} "
                f"sell={','.join(trends['sell_trends'])}"
            )
        ],
        "policy": [policy_line] if policy_line else [],
        "playbook": ["DeepSeek 趋势集合最优解已写入 harness policy"],
        "plan": ["intraday：验证 buy_trends / sell_trends 与落账趋势过滤对齐"],
        "summary": f"intraday_trends_llm buy={len(trends['buy_trends'])} sell={len(trends['sell_trends'])}",
        "llm_optimal": {**trends, "rationale": rationale},
    }
    return {
        "skipped": False,
        "planner": "deepseek",
        "provider": provider,
        "optimal": trends,
        "evidence": evidence,
        "raw": result,
    }


def apply_intraday_trends_llm_optimal_to_trend(
    merged: dict[str, Any],
    state: Any,
    *,
    settings: dict[str, Any],
) -> bool:
    optimal = _find_parsed_in_state(state, settings=settings)
    if not optimal:
        return False
    merged["buy_trends"] = list(optimal.get("buy_trends") or merged.get("buy_trends") or _DEFAULT_BUY_TRENDS)
    merged["sell_trends"] = list(optimal.get("sell_trends") or merged.get("sell_trends") or _DEFAULT_SELL_TRENDS)
    return True

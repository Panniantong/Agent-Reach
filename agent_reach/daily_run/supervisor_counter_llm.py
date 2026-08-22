# -*- coding: utf-8
"""LLM enrichment for Team-First supervisor counter-thesis factors."""

from __future__ import annotations

import json
from typing import Any, Optional


def counter_thesis_llm_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    team = (settings or {}).get("team") or {}
    cfg = team.get("counter_thesis_llm") or {}
    return cfg if isinstance(cfg, dict) else {}


def counter_thesis_llm_enabled(settings: Optional[dict[str, Any]]) -> bool:
    return counter_thesis_llm_cfg(settings).get("enabled", False) is True


def _compact_expert_context(
    snapshot: dict[str, Any],
    *,
    by_name: dict[str, float],
    base_factors: list[str],
    conflicts: list[str],
    label: str,
    max_experts: int = 8,
) -> dict[str, Any]:
    from agent_reach.daily_run.team import EXPERT_LABELS

    experts: list[dict[str, Any]] = []
    for row in snapshot.get("expert_results") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        experts.append(
            {
                "name": name,
                "label": EXPERT_LABELS.get(name, name),
                "score": by_name.get(name, row.get("score")),
                "summary": str(row.get("summary") or "")[:120],
                "success": row.get("success", True),
            }
        )
        if len(experts) >= max_experts:
            break

    macro_summary = str(snapshot.get("macro_summary") or "")[:160]
    sources = snapshot.get("sources") or {}
    source_bits = []
    for key in ("quote", "flow", "sentiment", "hot_news", "redfox"):
        detail = sources.get(key)
        if isinstance(detail, dict) and detail.get("summary"):
            source_bits.append(f"{key}: {str(detail['summary'])[:80]}")

    return {
        "consensus_label": label,
        "code": snapshot.get("code"),
        "name": snapshot.get("name"),
        "mss_final": snapshot.get("mss_final"),
        "mss_breakdown": snapshot.get("mss_breakdown"),
        "macro_summary": macro_summary or None,
        "source_summaries": source_bits[:4],
        "conflicts": conflicts[:3],
        "base_factors": base_factors[:4],
        "experts": experts,
    }


def enrich_counter_thesis_llm(
    snapshot: dict[str, Any],
    *,
    base_factors: list[str],
    conflicts: list[str],
    by_name: dict[str, float],
    label: str,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[list[str], str, bool, dict[str, Any]]:
    """
    Optionally refine counter-thesis via LLM.

    Returns (factors, thesis_markdown, recommend_downgrade, meta).
    """
    meta: dict[str, Any] = {"planner": "deterministic", "skipped": True}
    if label != "可做" or not counter_thesis_llm_enabled(settings):
        markdown = "反面检验：" + "；".join(base_factors[:3]) if base_factors else ""
        return list(base_factors), markdown, False, meta

    cfg = counter_thesis_llm_cfg(settings)
    context = _compact_expert_context(
        snapshot,
        by_name=by_name,
        base_factors=base_factors,
        conflicts=conflicts,
        label=label,
    )
    system = (
        "你是 A 股 Team-First Supervisor 的反面检验助手。"
        "在共识标签为「可做」时，基于专家评分与结构化因子，补充 2-4 条可验证的反面风险。"
        "不要重复已有因子；优先宏观/流动性/舆情/鉴别失败类风险。"
        '返回 JSON：{"counter_factors":["..."],"counter_thesis":"一句总述","recommend_downgrade":bool}。'
        "counter_factors 每条不超过 40 字；counter_thesis 不超过 60 字。"
    )

    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(cfg.get("provider") or "auto")
    if not resolve_chat_provider(provider):
        meta["reason"] = "no_llm_provider"
        markdown = "反面检验：" + "；".join(base_factors[:3]) if base_factors else ""
        return list(base_factors), markdown, False, meta

    payload = chat_json(
        system=system,
        user=json.dumps(context, ensure_ascii=False),
        provider=provider,
        model=cfg.get("model") or None,
        timeout=int(cfg.get("timeout_seconds") or 45),
        max_tokens=int(cfg.get("max_output_tokens") or 280),
    )
    if not isinstance(payload, dict):
        meta["reason"] = "llm_empty"
        markdown = "反面检验：" + "；".join(base_factors[:3]) if base_factors else ""
        return list(base_factors), markdown, False, meta

    llm_factors = [str(x).strip() for x in (payload.get("counter_factors") or []) if str(x).strip()]
    max_factors = int(cfg.get("max_factors") or 4)
    merged = list(dict.fromkeys([*base_factors, *llm_factors]))[:max_factors]
    thesis = str(payload.get("counter_thesis") or "").strip()
    if thesis:
        markdown = f"反面检验：{thesis}"
    else:
        markdown = "反面检验：" + "；".join(merged[:3])

    recommend = payload.get("recommend_downgrade")
    recommend_downgrade = recommend is True
    meta = {
        "planner": "llm",
        "skipped": False,
        "recommend_downgrade": recommend_downgrade,
        "llm_factor_count": len(llm_factors),
    }
    return merged, markdown, recommend_downgrade, meta

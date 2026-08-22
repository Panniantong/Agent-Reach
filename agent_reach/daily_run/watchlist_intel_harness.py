# -*- coding: utf-8
"""Watchlist announcement/news intel → harness playbook/plan."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def watchlist_intel_harness_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    wl = (settings or {}).get("watchlist") or {}
    nested = wl.get("intel") or {}
    if nested.get("harness_evolve") is False:
        return False
    if wl.get("intel_harness_evolve") is False:
        return False
    if wl.get("announcement_intel_enabled", True) is False:
        return False
    return wl.get("harness_evolve", True) is not False


def watchlist_intel_to_harness_evidence(
    intel_by_code: Optional[dict[str, Any]] = None,
    *,
    adjust: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    rows = dict(intel_by_code or {})
    if not rows:
        return {
            "memory": memory,
            "policy": policy,
            "playbook": playbook,
            "plan": plan,
            "summary": "watchlist intel empty",
        }

    negative_ann = 0
    negative_news = 0
    positive = 0
    for code, intel in rows.items():
        if not isinstance(intel, dict):
            continue
        sentiment = str(intel.get("sentiment") or "positive")
        name = intel.get("name") or code
        headline = str(intel.get("headline") or "").strip()
        if sentiment == "negative":
            negative_ann += 1
            playbook.append(f"watchlist 利空公告移出 {name}({code})：{headline[:60]}")
        elif sentiment == "negative_news":
            negative_news += 1
            memory.append(f"观察池 {name} 利空资讯：{headline[:48]}")
        else:
            positive += 1

    neg_removals = [
        c
        for c in (adjust or {}).get("changes") or []
        if c.get("action") == "remove" and "利空公告" in str(c.get("reason") or "")
    ]
    if neg_removals:
        memory.append(f"watchlist 因利空公告移出 {len(neg_removals)} 只")

    if negative_ann >= 2:
        policy.append("watchlist intel：多标的利空公告，明日优先防守、暂缓纳入")
    elif negative_ann == 1:
        policy.append("watchlist intel：出现利空公告，纳入前复核公告语义")

    if negative_news >= 2:
        plan.append("watchlist：资讯面偏空，观察池评分降权已生效")

    if positive >= 3 and negative_ann == 0:
        playbook.append(f"watchlist 公告/资讯偏暖 {positive} 只，维持 intel 加分策略")

    summary = (
        f"watchlist intel pos={positive} neg_ann={negative_ann} neg_news={negative_news}"
    )
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def apply_watchlist_intel_harness_refinement(
    intel_by_code: Optional[dict[str, Any]] = None,
    *,
    adjust: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not watchlist_intel_harness_enabled(settings):
        return {"skipped": True, "reason": "watchlist intel harness disabled", "job": "watchlist_intel"}
    rows = dict(intel_by_code or {})
    if not rows:
        return {"skipped": True, "reason": "no watchlist intel", "job": "watchlist_intel"}
    evidence = watchlist_intel_to_harness_evidence(rows, adjust=adjust)
    if not any(evidence.get(key) for key in ("memory", "policy", "playbook", "plan")):
        return {"skipped": True, "reason": "neutral intel", "job": "watchlist_intel"}
    return apply_skill_refinement("watchlist_intel", evidence, settings=settings)

# -*- coding: utf-8
"""Watchlist adjust outcomes → harness playbook/plan."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def watchlist_adjust_to_harness_evidence(adjust: dict[str, Any]) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    applied = bool(adjust.get("applied"))
    message = str(adjust.get("message") or "")
    changes = list(adjust.get("changes") or [])

    if not applied:
        memory.append(f"watchlist 未调整：{message}")
        if "上限" in message or "max_total" in message.lower():
            plan.append("watchlist：观察池/总标的触顶，明日优先卖出或缩减持仓")
        return {
            "memory": memory,
            "policy": policy,
            "playbook": playbook,
            "plan": plan,
            "summary": f"watchlist skipped {message[:40]}",
        }

    adds = [c for c in changes if c.get("action") == "add"]
    removes = [c for c in changes if c.get("action") == "remove"]
    memory.append(f"watchlist 调整 {len(changes)} 项：+{len(adds)} -{len(removes)}")

    for change in changes[:6]:
        action = change.get("action")
        name = change.get("name") or change.get("code") or "?"
        code = change.get("code") or ""
        reason = change.get("reason") or ""
        if action == "add":
            playbook.append(f"watchlist 纳入 {name}({code})：{reason[:80]}")
        elif action == "remove":
            playbook.append(f"watchlist 移出 {name}({code})：{reason[:80]}")
            if "否决线" in reason or "评分" in reason:
                memory.append(f"观察池移出弱势标的 {name}：{reason[:60]}")
        elif action == "reorder":
            playbook.append(f"watchlist 重排：{reason[:80]}")

    if len(adds) > 3:
        plan.append("watchlist：单日纳入过多，检查 hot_topic_adjust 阈值")

    summary = f"watchlist changes={len(changes)} applied=True"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def apply_watchlist_adjust_harness_refinement(
    adjust: dict[str, Any] | None,
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not adjust:
        return {"skipped": True, "reason": "no watchlist adjust", "job": "watchlist_adjust"}
    wl_cfg = (settings or {}).get("watchlist") or {}
    if wl_cfg.get("harness_evolve", True) is False:
        return {"skipped": True, "reason": "watchlist.harness_evolve disabled", "job": "watchlist_adjust"}
    evidence = watchlist_adjust_to_harness_evidence(adjust)
    return apply_skill_refinement("watchlist_adjust", evidence, settings=settings)

# -*- coding: utf-8
"""Intraday scan / trade findings → harness self-evolution."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def intraday_to_harness_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    scan_block = payload.get("scan") or payload
    scan = scan_block.get("scan") if isinstance(scan_block, dict) and "scan" in scan_block else scan_block
    if not isinstance(scan, dict):
        scan = {}

    state = scan_block.get("state") if isinstance(scan_block, dict) else {}
    if isinstance(state, dict):
        scans = state.get("scans") or []
    else:
        scans = payload.get("scans") or []

    scan_id = scan.get("scan_id") or f"S{len(scans)}"
    name = scan.get("name") or scan.get("code") or "标的"
    mss = scan.get("mss_final")
    trend = scan_block.get("trend") or payload.get("trend")
    lookback = scan_block.get("lookback_mss") or payload.get("lookback_mss")

    if mss is not None:
        memory.append(f"盘中 {scan_id} {name} MSS={mss} trend={trend or '—'}")
    if lookback is not None:
        memory.append(f"Lookback MSS={float(lookback):.0f}（{scan_id}）")

    scan_count = len(scans) if scans else payload.get("scan_count")
    if scan_count is not None:
        if int(scan_count) < 3:
            memory.append("盘中扫描偏少：intraday 次数不足，下日 trade_min_scans 可降至 2")
            plan.append(f"intraday：{name} 扫描仅 {scan_count} 次，确认 cron S3–S15")
        elif int(scan_count) >= 13:
            playbook.append(f"盘中扫描充足（{scan_count} 次），Lookback 权重可信")

    source = scan.get("source")
    if source and source != "morning" and scan_id == "S2":
        memory.append("S2 未标记 morning 来源")
        plan.append("morning：08:00 全量早盘应写入 record_morning_scan(source=morning)")

    trade = payload.get("trade")
    if isinstance(trade, dict):
        decision = trade.get("decision") or trade
        if isinstance(decision, dict):
            action = decision.get("action")
            reasoning = str(decision.get("reasoning") or "")
            if action and action != "hold":
                playbook.append(f"盘中 {scan_id} {action}：{reasoning[:120]}")
            if decision.get("friction_blocked"):
                memory.append("减少频繁调仓：摩擦成本过高时提高 friction_min_return_pct")
            if decision.get("blocked") and "macro" in reasoning.lower():
                memory.append("宏观一票否决生效：维持高现金，禁止接飞刀")

    if payload.get("skipped"):
        reason = str(payload.get("reason") or "")
        memory.append(f"intraday skipped：{reason}")
        if "上限" in reason or "MAX" in reason.upper():
            plan.append("intraday：扫描达上限，确认 S15 是否落在 15:00")

    summary = f"intraday {scan_id} {name} scans={scan_count}"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def apply_intraday_harness_refinement(
    payload: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    evidence = intraday_to_harness_evidence(payload)
    if not any(evidence.get(k) for k in ("memory", "policy", "playbook", "plan")):
        return {"skipped": True, "reason": "empty evidence", "job": "intraday"}
    return apply_skill_refinement("intraday", evidence, settings=settings)

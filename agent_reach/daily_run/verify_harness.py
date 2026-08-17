# -*- coding: utf-8
"""Verify snapshot deviations → harness self-evolution."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement, merge_harness_evidence


def verify_to_harness_evidence(verify: dict[str, Any]) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    name = verify.get("name") or verify.get("code") or "标的"
    if verify.get("summary"):
        memory.append(f"verify {name}：{verify['summary']}")

    for dev in verify.get("deviations") or []:
        text = str(dev)
        memory.append(f"偏差：{text}" if not text.startswith("偏差") else text)
        if "锚点阈值" in text or "价格变动" in text:
            policy.append("当预测标的收盘价格变动绝对值超过锚点阈值8.0%时，触发偏差记录")
            memory.append("MSS 预测偏离：下日调低进攻阈值或缩窄仓位")
        if "MSS" in text and ("预测" in text or "低于" in text or "高于" in text):
            memory.append("MSS 预测偏离：下日调低进攻阈值或缩窄仓位")
            playbook.append("增大 mss_forecast.base_spread 或运行 daily-run optimize")

    if verify.get("mss_within_prediction") is False:
        memory.append("MSS 预测偏离：下日调低进攻阈值或缩窄仓位")

    if verify.get("verdict_changed"):
        vb = verify.get("verdict_baseline")
        vc = verify.get("verdict_current")
        memory.append(f"标签变更 {vb}→{vc}：{name}")

    for rec in verify.get("recommendations") or []:
        line = str(rec).strip()
        if not line:
            continue
        playbook.append(f"verify 建议：{line}")
        if "高现金" in line or "取消" in line and "买入" in line:
            memory.append("维持高现金：禁止接飞刀，取消一切买入")
        if "建仓" in line or "进攻" in line:
            plan.append(f"verify 跟进：{line}")

    open_dev = len(verify.get("deviations") or [])
    summary = f"verify {name} deviations={open_dev} hit={verify.get('mss_within_prediction')}"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def apply_verify_harness_refinement(
    verify: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    forecast_review: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    parts = [verify_to_harness_evidence(verify)]
    if forecast_review:
        from agent_reach.daily_run.close_improve_harness import forecast_review_to_harness_evidence

        parts.append(forecast_review_to_harness_evidence(forecast_review))
    evidence = merge_harness_evidence(*parts)
    return apply_skill_refinement("verify", evidence, settings=settings, enabled_flag="close_improvements")

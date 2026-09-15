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
        if "冲高回落" in text or ("可做" in text and "观察" in text):
            from agent_reach.daily_run.session_verdict_guard_policy import format_session_verdict_policy_line

            policy.append(
                format_session_verdict_policy_line(
                    {
                        "price_pullback_pct": 1.9,
                        "mss_pullback_pts": 1.9,
                    },
                    rationale="verify 偏差：早盘可做后回落",
                )
            )
            memory.append("冲高回落偏差：session_verdict_guards 收紧 price_pullback / mss_pullback")
        if "跌幅" in text and ("无预警" in text or "暴跌" in text or "哨兵" in text):
            from agent_reach.daily_run.session_verdict_guard_policy import format_watchlist_drawdown_policy_line

            policy.append(
                format_watchlist_drawdown_policy_line(
                    {"yellow_pct": -2.5, "red_pct": -4.0},
                    rationale="verify 偏差：观察池跌幅预警不足",
                )
            )
            memory.append("观察池跌幅偏差：watchlist_drawdown 收紧 yellow/red 阈值")
        if "观望正确" in text or ("观望" in text and "正确" in text):
            memory.append("观望正确：session_verdict 维持或略收紧冲高回落阈值")
            playbook.append("session_verdict：正样本观望，保留 S4+ 降级 guard")

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

    block_kind = str(verify.get("primary_block_kind") or verify.get("block_kind") or "")
    if block_kind == "sell_week_open_hold_debounce":
        memory.append("澜起类持有计划：defensive_trim 被 hold_debounce 阻断，非宏观否决")
        policy.append("卡片脚注 Harness 有效参数 ≠ 宏观否决触发次数")
    elif block_kind == "sell_defensive_trim":
        memory.append("防御减仓被 rebound/recovery 保护阻断时，检查 hold_debounce 与 plan 一致性")

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

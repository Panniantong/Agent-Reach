# -*- coding: utf-8
"""Data audit findings → harness self-evolution."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.auditor import AuditResult
from agent_reach.daily_run.harness_skill_base import apply_skill_refinement


def audit_to_harness_evidence(audit: AuditResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(audit, AuditResult):
        issues = list(audit.issues)
        warnings = list(audit.warnings)
        passed = audit.passed
        structured = audit.structured_review_complete
    else:
        issues = list(audit.get("issues") or [])
        warnings = list(audit.get("warnings") or [])
        passed = bool(audit.get("passed", True))
        structured = audit.get("structured_review_complete", True)

    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    if not passed:
        memory.append(f"数据审计未通过：{'；'.join(issues[:3])}")

    for issue in issues:
        text = str(issue)
        memory.append(f"audit issue：{text}")
        if "过期" in text or "as_of" in text:
            plan.append("修复 snapshot as_of / 重新拉 quote")
            playbook.append("推送/调仓前确认 max_snapshot_age_hours 内数据")
        if "缺少数据来源" in text or "quote" in text:
            plan.append("补全 sources.quote / 运行 doctor")
            playbook.append("data_audit：required_source_categories 须含 quote/flow/sentiment")
        if "占位" in text:
            plan.append("替换 sources 占位内容为真实摘要")
        if "锚点" in text or "偏差" in text:
            memory.append("偏差：价格变动超过锚点阈值")
            policy.append("block_on_price_deviation 生效时禁止依赖失真价格调仓")

    for warn in warnings:
        text = str(warn)
        playbook.append(f"audit warn：{text}")
        if "覆盖率" in text:
            plan.append("提升 quote_fetch 覆盖率或降低 min_quote_coverage_pct 门槛")
        if "fallback" in text or "成本价" in text:
            memory.append("技术面因子拖累 MSS：缺失 ma20/position_20d 会导致技术分降级为中性")

    if structured is False:
        memory.append("结构化复核未完成：标签上限「观察」，禁止激进买入")

    summary = f"data_audit passed={passed} issues={len(issues)} warnings={len(warnings)}"
    verification_signals: list[str] = []
    if not passed:
        verification_signals.append("audit_failed")
    if structured is False:
        verification_signals.append("structured_review_incomplete")
    if issues:
        verification_signals.append(f"audit_issues={len(issues)}")
    if warnings:
        verification_signals.append(f"audit_warnings={len(warnings)}")

    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
        "audit_passed": passed,
        "structured_review_complete": structured,
        "issues": issues,
        "warnings": warnings,
        "verification_signals": verification_signals,
    }


def apply_data_audit_harness_refinement(
    audit: AuditResult | dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    evidence = audit_to_harness_evidence(audit)
    return apply_skill_refinement("data_audit", evidence, settings=settings, enabled_flag="data_audit")

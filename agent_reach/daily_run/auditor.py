# -*- coding: utf-8 -*-
"""Data authenticity audit before analysis or trading."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class AuditResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    structured_review_complete: bool = True

    def summary(self) -> str:
        if self.passed:
            return "数据审计通过"
        return "数据审计未通过：" + "；".join(self.issues)


def run_data_audit(
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    *,
    doctor_channels: Optional[dict[str, dict]] = None,
) -> AuditResult:
    """Validate snapshot freshness, sources, price anchors, and doctor readiness."""
    audit_cfg = settings.get("data_audit", {})
    thresholds = settings.get("thresholds", {})
    issues: list[str] = []
    warnings: list[str] = []
    structured_review_complete = True

    as_of_raw = snapshot.get("as_of")
    if not as_of_raw:
        issues.append("缺少 as_of 时间戳")
    else:
        try:
            as_of = _parse_dt(as_of_raw)
            age_hours = (datetime.now(timezone.utc) - as_of).total_seconds() / 3600
            max_age = float(thresholds.get("max_snapshot_age_hours", 24))
            if age_hours < -0.1:
                issues.append("as_of 时间戳在未来")
            elif age_hours > max_age:
                issues.append(f"数据过期（{age_hours:.1f}h > {max_age}h）")
        except ValueError as exc:
            issues.append(str(exc))

    required_cats = audit_cfg.get("required_source_categories", [])
    sources = snapshot.get("sources") or {}
    if isinstance(sources, dict):
        present = set(sources.keys())
    elif isinstance(sources, list):
        present = set(sources)
    else:
        present = set()
        issues.append("sources 格式无效")

    missing_cats = [c for c in required_cats if c not in present]
    if missing_cats:
        issues.append(f"缺少数据来源类别：{', '.join(missing_cats)}")
        if "quote" in missing_cats:
            structured_review_complete = False

    for cat in required_cats:
        if cat in present and isinstance(sources, dict):
            detail = sources.get(cat)
            if not detail:
                warnings.append(f"来源类别 {cat} 为空")
            elif isinstance(detail, dict):
                summary = str(detail.get("summary", ""))
                if _is_placeholder(summary):
                    issues.append(f"来源 {cat} 仍为占位内容：{summary or '空'}")

    if snapshot.get("has_cost_fallback"):
        warnings.append("部分标的使用成本价 fallback，行情可能过期")
        structured_review_complete = False

    quote_meta = snapshot.get("quote_fetch") or {}
    coverage_pct = quote_meta.get("coverage_pct")
    min_cov = float(audit_cfg.get("min_quote_coverage_pct", 0.8))
    if coverage_pct is not None:
        cov = float(coverage_pct) / 100.0
        if cov < min_cov:
            msg = f"行情覆盖率 {coverage_pct}% 低于阈值 {min_cov:.0%}"
            mode = audit_cfg.get("quote_coverage_mode", "block")
            if mode == "block":
                issues.append(msg)
            else:
                warnings.append(msg)
        fetch_errors = quote_meta.get("errors") or {}
        if fetch_errors:
            sample = ", ".join(f"{k}: {v}" for k, v in list(fetch_errors.items())[:3])
            warnings.append(f"部分标的报价失败：{sample}")

    ref_price = snapshot.get("reference_price")
    live_price = snapshot.get("price")
    if ref_price is not None and live_price is not None:
        try:
            ref = float(ref_price)
            live = float(live_price)
            if ref > 0:
                dev = abs(live - ref) / ref
                from agent_reach.daily_run.harness_policy import threshold_default

                max_dev = float(threshold_default(settings, "max_price_deviation_pct"))
                if dev > max_dev:
                    msg = f"价格锚点偏差 {dev:.1%} 超过阈值 {max_dev:.1%}"
                    if audit_cfg.get("block_on_price_deviation", True):
                        issues.append(msg)
                    else:
                        warnings.append(msg)
        except (TypeError, ValueError):
            issues.append("reference_price 或 price 无法解析为数字")

    code = snapshot.get("code")
    name = snapshot.get("name")
    if code and name:
        code_str = str(code).strip()
        if code_str not in str(name) and str(name) not in code_str:
            # loose check — warn only unless explicit mismatch flag
            if snapshot.get("identity_mismatch"):
                issues.append(f"标的身份不一致：{code} vs {name}")

    if doctor_channels and audit_cfg.get("required_doctor_channels"):
        for ch in audit_cfg["required_doctor_channels"]:
            info = doctor_channels.get(ch)
            if not info or info.get("status") != "ok":
                warnings.append(f"doctor 渠道 {ch} 未就绪")

    if snapshot.get("structured_review_complete") is False:
        structured_review_complete = False
        warnings.append("未完成结构化复核（仅 Web 候选，未校验关键字段）")

    passed = len(issues) == 0

    return AuditResult(
        passed=passed,
        issues=issues,
        warnings=warnings,
        structured_review_complete=structured_review_complete,
    )


def _parse_dt(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_placeholder(text: str) -> bool:
    return not text or text.strip() in ("待更新", "pending", "n/a", "N/A")

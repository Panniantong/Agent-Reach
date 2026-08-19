# -*- coding: utf-8 -*-
"""Build markdown reports and run the daily-run pipeline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from agent_reach.daily_run.auditor import AuditResult, run_data_audit
from agent_reach.daily_run.quality_gate import GateResult, validate_report
from agent_reach.daily_run.settings import effective_settings, load_settings
from agent_reach.daily_run.harness_display import format_mss_breakdown_lines
from agent_reach.daily_run.verdict import VerdictResult, compute_verdict, fuse_verdict_with_team

_MSS_BREAKDOWN_LABELS = {}  # backward compat for tests importing pipeline labels


def _format_mss_breakdown_lines(breakdown: dict[str, Any]) -> list[str]:
    return format_mss_breakdown_lines(breakdown)


def evaluate_snapshot(
    snapshot: dict[str, Any],
    settings: Optional[dict[str, Any]] = None,
    *,
    doctor_channels: Optional[dict[str, dict]] = None,
) -> dict[str, Any]:
    """Run audit + verdict + quality gate on a market snapshot."""
    cfg = effective_settings(settings)
    audit = run_data_audit(snapshot, cfg, doctor_channels=doctor_channels)
    enriched = dict(snapshot)
    enriched["audit_passed"] = audit.passed
    enriched["structured_review_complete"] = audit.structured_review_complete

    verdict = compute_verdict(enriched, cfg)
    if enriched.get("team_review") or enriched.get("team_consensus_label"):
        verdict = fuse_verdict_with_team(verdict, enriched, cfg)
    report = build_report(enriched, audit, verdict, cfg)
    gate = validate_report(report, cfg)

    if gate.downgraded and gate.missing_fields:
        labels = cfg.get("verdict_labels", {})
        report["verdict"] = labels.get("watch", "观察")
        report["confidence"] = "低"
        report["downgrade_reasons"] = list(report.get("downgrade_reasons", [])) + [
            "质量门禁：缺少字段 " + ", ".join(gate.missing_fields)
        ]

    return {
        "audit": audit,
        "verdict": verdict,
        "report": report,
        "gate": gate,
        "settings_version": cfg.get("version"),
    }


def build_report(
    snapshot: dict[str, Any],
    audit: AuditResult,
    verdict: VerdictResult,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Structured report dict for gate validation and markdown rendering."""
    evidence = []
    for cat, detail in (snapshot.get("sources") or {}).items():
        if isinstance(detail, dict):
            evidence.append(
                f"- **{cat}**: {detail.get('summary', detail.get('url', 'ok'))}"
            )
        else:
            evidence.append(f"- **{cat}**: {detail}")

    breakdown = snapshot.get("mss_breakdown") or {}
    breakdown_lines = _format_mss_breakdown_lines(breakdown)
    from agent_reach.daily_run.harness_display import format_effective_thresholds_markdown

    threshold_policy_md = format_effective_thresholds_markdown(settings)

    prior_close_mss = snapshot.get("prior_close_mss")
    prior_close_delta = None
    if prior_close_mss is not None:
        prior_close_delta = round(float(verdict.mss_final) - float(prior_close_mss), 2)

    return {
        "as_of": snapshot.get("as_of") or datetime.now(timezone.utc).isoformat(),
        "code": snapshot.get("code"),
        "name": snapshot.get("name"),
        "verdict": verdict.verdict,
        "confidence": verdict.confidence,
        "mss_final": verdict.mss_final,
        "mss_breakdown": breakdown,
        "prior_close_mss": prior_close_mss,
        "prior_close_delta": prior_close_delta,
        "prior_close_date": snapshot.get("prior_close_date"),
        "prior_close_verdict": snapshot.get("prior_close_verdict"),
        "prior_close_source": snapshot.get("prior_close_source"),
        "entry_price": verdict.entry_price,
        "stop_loss_price": verdict.stop_loss_price,
        "invalidation": verdict.invalidation,
        "reasoning": verdict.reasoning,
        "downgrade_reasons": verdict.downgrade_reasons,
        "blocked": verdict.blocked,
        "audit_passed": audit.passed,
        "audit_summary": audit.summary(),
        "audit_warnings": audit.warnings,
        "evidence_chain": "\n".join(evidence) if evidence else snapshot.get("evidence_chain", ""),
        "mss_breakdown_text": "\n".join(breakdown_lines),
        "threshold_policy_md": threshold_policy_md,
        "portfolio": snapshot.get("portfolio"),
        "watchlist": snapshot.get("watchlist"),
        "macro_summary": snapshot.get("macro_summary"),
        "report_type": snapshot.get("report_type", "premarket"),
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render Feishu lark_md body from structured report."""
    from agent_reach.daily_run.prior_close import format_prior_close_line

    lines = [
        f"**结论：{report.get('verdict')}**（置信度：{report.get('confidence')}）",
        "",
        f"**MSS：** {report.get('mss_final')} 分",
    ]
    prior_line = format_prior_close_line(report)
    if prior_line:
        lines.extend(["", prior_line])
    if report.get("mss_breakdown_text"):
        lines.extend(["", "**MSS 拆解：**", report["mss_breakdown_text"]])
    if report.get("threshold_policy_md"):
        lines.extend(["", report["threshold_policy_md"]])

    lines.extend([
        "",
        f"**推理：** {report.get('reasoning')}",
        "",
        f"**失效条件：** {report.get('invalidation')}",
    ])

    if report.get("entry_price") is not None:
        lines.append(f"**参考入场：** {report['entry_price']}")
    if report.get("stop_loss_price") is not None:
        lines.append(f"**止损参考：** {report['stop_loss_price']}")

    if report.get("downgrade_reasons"):
        lines.extend(["", "**降级原因：**"])
        for r in report["downgrade_reasons"]:
            lines.append(f"- {r}")

    lines.extend([
        "",
        f"**数据审计：** {report.get('audit_summary')}",
    ])
    if report.get("audit_warnings"):
        lines.append("**审计警告：**")
        for w in report["audit_warnings"]:
            lines.append(f"- {w}")

    if report.get("evidence_chain"):
        lines.extend(["", "**证据链：**", report["evidence_chain"]])

    if report.get("macro_summary"):
        lines.extend(["", "**宏观摘要：**", str(report["macro_summary"])])

    if report.get("portfolio"):
        lines.extend(["", "**持仓：**", _fmt_json_block(report["portfolio"])])

    if report.get("watchlist"):
        lines.extend(["", "**观察池：**", _fmt_json_block(report["watchlist"])])

    if report.get("blocked"):
        lines.extend(["", "⚠️ **交易阻断：** 当前标签不允许执行买入操作"])

    return "\n".join(lines)


def push_report(
    evaluation: dict[str, Any],
    *,
    title: Optional[str] = None,
    template: Optional[str] = None,
    config=None,
) -> dict[str, Any]:
    """Push evaluated report to Feishu if quality gate allows."""
    from agent_reach.config import Config
    from agent_reach.integrations.feishu import FeishuError, send_card

    gate: GateResult = evaluation["gate"]
    audit: AuditResult = evaluation["audit"]
    report = evaluation["report"]
    settings = load_settings()

    if not gate.passed:
        raise FeishuError(f"质量门禁未通过：{gate.summary()}")
    if not audit.passed and settings.get("data_audit", {}).get("block_on_audit_fail", True):
        raise FeishuError(f"数据审计未通过：{audit.summary()}")

    cfg = config or Config()
    report_type = report.get("report_type", "premarket")
    templates = settings.get("report", {})
    tpl = template or templates.get(f"feishu_template_{report_type}", "blue")

    if not title:
        name = report.get("name") or report.get("code") or "大盘"
        title = f"📈 股票大师 · {name} · {report.get('verdict')}"

    markdown = render_markdown(report)
    return send_card(cfg, title, markdown, template=tpl)


def _fmt_json_block(data: Any) -> str:
    return "```\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```"

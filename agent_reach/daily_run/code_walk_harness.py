# -*- coding: utf-8
"""Agent code walk + harness self-evolution (skill runtime)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.close_code_review import (
    CodeFinding,
    CodeReviewResult,
    DEFAULT_WALK_MODULES,
    list_walk_module_names,
    run_close_code_review,
)
from agent_reach.daily_run.settings import effective_settings, load_settings

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger("agent_reach.daily_run.code_walk_harness")


@dataclass
class CodeWalkReport:
    review: CodeReviewResult
    static_findings: list[CodeFinding] = field(default_factory=list)
    harness_refinement: dict[str, Any] = field(default_factory=dict)
    effective_overlay: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "review": self.review.to_dict(),
            "static_findings": [f.to_dict() for f in self.static_findings],
            "harness_refinement": self.harness_refinement,
            "effective_overlay": self.effective_overlay,
            "open_findings": len([f for f in self.all_findings() if not f.fixed]),
        }

    def all_findings(self) -> list[CodeFinding]:
        return list(self.review.findings) + list(self.static_findings)


def _finding_key(finding: CodeFinding) -> str:
    return f"{finding.area}|{finding.title}|{finding.detail[:80]}"


def finding_to_harness_lines(finding: CodeFinding) -> tuple[list[str], list[str], list[str], list[str]]:
    """Map a code-walk finding to harness memory/policy/playbook/plan lines."""
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []
    area = finding.area
    title = finding.title
    detail = finding.detail
    blob = f"{title} {detail}"

    if area == "harness" and "overlay" in title:
        policy.append("代码走读：调用方须 effective_settings()，否则阈值/锁仓/schedule 不走 harness 进化")
        plan.append("排查 load_settings() 直传 consumers；改为 effective_settings()")
    elif area == "harness" and "静态配置" in title:
        playbook.append(f"静态 JSON 移除 harness 进化项（{detail[:120]}）")
        policy.append("harness 模式下进化项仅由 memory/policy/playbook 驱动，禁止写回 daily_run_settings.json")
    elif area == "harness" and "macro_veto" in title:
        memory.append("代码走读：defensive_trim 时 macro_veto 须 ≤30，检查 overlay 与 memory 是否同步")
    elif area == "harness" and "consumer" in title.lower() or "绕过" in title:
        policy.append(f"代码走读：{detail}；消费者须 threshold_default / runtime_*_default / effective_days_held")
        plan.append(f"修复 {title}：接入 harness helper fallback")
    elif area == "portfolio" and "days_held" in title:
        memory.append("代码走读：days_held 须由 acquired_date 重算；load_portfolio 须 sync_portfolio_holding_days")
        playbook.append("禁止裸读 days_held 做锁仓/复盘判断；统一 effective_days_held()")
    elif area == "portfolio" and "acquired_date" in title:
        memory.append("代码走读：买入须写 acquired_date；缺失则 T+1 锁仓不可信")
        plan.append("补写 portfolio.json acquired_date 或走 auto_fix")
    elif finding.fixed and finding.fix_note:
        playbook.append(f"代码走读已修复：{finding.fix_note[:160]}")
    elif finding.severity == "high":
        memory.append(f"代码走读 high：{title} — {detail[:160]}")
        plan.append(f"待修复：{title}")
    elif finding.severity == "medium" and area in ("harness", "portfolio", "intraday"):
        memory.append(f"代码走读：{title} — {detail[:120]}")

    if "MSS 预测偏离" in blob or "预测未命中" in blob:
        memory.append("MSS 预测偏离：下日调低进攻阈值或缩窄仓位")
    if "维持高现金" in blob or "现金比例" in title:
        memory.append("维持高现金：禁止接飞刀，取消一切买入")

    return memory, policy, playbook, plan


def findings_to_harness_evidence(
    findings: list[CodeFinding],
    *,
    fixes: Optional[list[str]] = None,
) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []
    seen: set[str] = set()

    def _extend(kind: str, lines: list[str]) -> None:
        for line in lines:
            if not line or line in seen:
                continue
            seen.add(line)
            if kind == "memory":
                memory.append(line)
            elif kind == "policy":
                policy.append(line)
            elif kind == "playbook":
                playbook.append(line)
            else:
                plan.append(line)

    for finding in findings:
        m, p, pb, pl = finding_to_harness_lines(finding)
        _extend("memory", m)
        _extend("policy", p)
        _extend("playbook", pb)
        _extend("plan", pl)

    for fix in fixes or []:
        line = f"代码走读已修复：{fix}"
        _extend("playbook", [line])

    open_high = [f for f in findings if not f.fixed and f.severity == "high"]
    summary = f"code_walk findings={len(findings)} open_high={len(open_high)} fixes={len(fixes or [])}"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def scan_static_wiring(settings: Optional[dict[str, Any]] = None) -> list[CodeFinding]:
    """Static checks outside close portfolio state (skill P1/P2)."""
    from agent_reach.daily_run.harness_policy import harness_evolution_mode, list_static_config_pollution

    cfg = settings or load_settings()
    findings: list[CodeFinding] = []

    if harness_evolution_mode(cfg) == "harness":
        pollution = list_static_config_pollution(cfg)
        if pollution:
            shown = ", ".join(pollution[:10])
            if len(pollution) > 10:
                shown += "…"
            findings.append(
                CodeFinding(
                    "harness",
                    "medium",
                    "静态配置仍含 harness 进化项",
                    shown,
                )
            )

    try:
        import agent_reach.daily_run as pkg

        base = Path(pkg.__file__).resolve().parent
    except (ImportError, TypeError):
        return findings

    evolved_reads = (
        '.get("macro_veto"',
        '.get("aggressive_entry"',
        '.get("holding_lock_days"',
        '.get("days_held")',
    )
    helpers = (
        "threshold_default",
        "min_cash_ratio_default",
        "runtime_int_default",
        "effective_days_held",
        "effective_settings",
    )
    skip = {"harness_policy.py", "settings.py", "optimizer.py", "backtest.py", "code_walk_harness.py"}

    for name in list_walk_module_names(cfg):
        if name in skip:
            continue
        path = base / name
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        if any(r in source for r in evolved_reads) and not any(h in source for h in helpers):
            findings.append(
                CodeFinding(
                    "harness",
                    "medium",
                    f"{name} 可能绕过 harness 读阈值",
                    "须 threshold_default / runtime_*_default / effective_settings",
                )
            )
        if '.get("days_held")' in source and "effective_days_held" not in source and name not in (
            "portfolio_manager.py",
            "close_code_review.py",
        ):
            findings.append(
                CodeFinding(
                    "portfolio",
                    "medium",
                    f"{name} 直接读 days_held",
                    "业务判断应走 effective_days_held() 或 load 时 sync",
                )
            )
    return findings


def apply_code_walk_harness_refinement(
    result: CodeReviewResult,
    *,
    settings: Optional[dict[str, Any]] = None,
    extra_findings: Optional[list[CodeFinding]] = None,
) -> dict[str, Any]:
    """Write code-walk findings into harness memory/policy/playbook (self-evolution)."""
    from agent_reach.daily_run.harness import refine_after_job

    cfg = settings or load_settings()
    harness_cfg = cfg.get("harness") or {}
    if harness_cfg.get("enabled") is False:
        return {"skipped": True, "reason": "harness disabled"}

    review_cfg = cfg.get("close_code_review") or {}
    if review_cfg.get("harness_evolve_on_walk", True) is False:
        return {"skipped": True, "reason": "harness_evolve_on_walk disabled"}

    all_findings = list(result.findings) + list(extra_findings or [])
    if not all_findings and not result.fixes_applied:
        return {"skipped": True, "reason": "no findings"}

    evidence = findings_to_harness_evidence(all_findings, fixes=result.fixes_applied)
    refinement = refine_after_job("code_walk", evidence=evidence, settings=cfg)
    if not refinement.get("skipped"):
        try:
            from agent_reach.daily_run.harness import refine_after_job_llm_summarize

            summarize = refine_after_job_llm_summarize(
                "code_walk",
                evidence=evidence,
                settings=cfg,
                layer_a_result=refinement,
            )
            if summarize:
                refinement["llm_summarize"] = summarize
        except Exception as exc:
            logger.warning("daily-run code_walk llm_summarize failed: {}", exc)
    return refinement


def run_agent_code_walk(
    *,
    portfolio: Optional[dict[str, Any]] = None,
    snapshot: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
    scans: Optional[list[dict[str, Any]]] = None,
    trades: Optional[list[dict[str, Any]]] = None,
    walk_source: bool = True,
    evolve_harness: bool = True,
) -> CodeWalkReport:
    """Full skill runtime: review + static scan + harness refine + overlay snapshot."""
    raw = load_settings()
    cfg = effective_settings(settings or raw)

    if portfolio is None:
        try:
            from agent_reach.daily_run.snapshot_builder import load_portfolio

            portfolio = load_portfolio()
        except FileNotFoundError:
            portfolio = {"holdings": [], "watchlist": [], "cash": 0, "total": 0, "cash_ratio": 1}

    snap = dict(snapshot or {})
    review_cfg = dict(cfg.get("close_code_review") or {})
    if walk_source:
        review_cfg["walk_on_close"] = True
    # Single refine at end of run_agent_code_walk (includes static findings).
    review_cfg["harness_evolve_on_walk"] = False
    cfg = dict(cfg)
    cfg["close_code_review"] = review_cfg

    review = run_close_code_review(
        portfolio=portfolio,
        snapshot=snap,
        settings=cfg,
        scans=scans,
        trades=trades,
    )

    static_findings = scan_static_wiring(raw)
    for finding in static_findings:
        if _finding_key(finding) not in {_finding_key(f) for f in review.findings}:
            review.findings.append(finding)

    harness_refinement: dict[str, Any] = {}
    if evolve_harness:
        harness_refinement = apply_code_walk_harness_refinement(
            review,
            settings=cfg,
            extra_findings=static_findings,
        )
        review.harness_refinement = harness_refinement

    effective_after = effective_settings(raw)
    overlay = dict(effective_after.get("harness_runtime") or {})
    return CodeWalkReport(
        review=review,
        static_findings=static_findings,
        harness_refinement=harness_refinement,
        effective_overlay={
            "threshold_overlay": overlay.get("threshold_overlay"),
            "runtime_overlay": overlay.get("runtime_overlay"),
            "forecast_overlay": overlay.get("forecast_overlay"),
            "trade_signals": overlay.get("trade_signals"),
        },
    )


def render_code_walk_markdown(report: CodeWalkReport) -> str:
    from agent_reach.daily_run.close_code_review import render_code_review_markdown

    lines = [render_code_review_markdown(report.review).rstrip()]
    ref = report.harness_refinement or {}
    if ref and not ref.get("skipped"):
        lines.append("")
        lines.append("**Harness 自进化（code_walk）**")
        lines.append(f"- refinement_id: `{ref.get('refinement_id', '')}`")
        lines.append(f"- changes: {ref.get('changes', 0)}")
    elif ref.get("skipped"):
        lines.append("")
        lines.append(f"_Harness refine skipped: {ref.get('reason', '')}_")
    if report.effective_overlay.get("threshold_overlay"):
        lines.append("")
        lines.append("**Effective overlay 快照**")
        lines.append("```json")
        lines.append(json.dumps(report.effective_overlay, ensure_ascii=False, indent=2))
        lines.append("```")
    return "\n".join(lines).strip() + "\n"

# -*- coding: utf-8
"""Agent code walk + harness self-evolution (skill runtime)."""

from __future__ import annotations

import json
import re
import subprocess
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
    macro_findings: list[CodeFinding] = field(default_factory=list)
    diff_findings: list[CodeFinding] = field(default_factory=list)
    diff_review: dict[str, Any] = field(default_factory=dict)
    harness_refinement: dict[str, Any] = field(default_factory=dict)
    effective_overlay: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "review": self.review.to_dict(),
            "static_findings": [f.to_dict() for f in self.static_findings],
            "macro_findings": [f.to_dict() for f in self.macro_findings],
            "harness_refinement": self.harness_refinement,
            "effective_overlay": self.effective_overlay,
            "open_findings": len([f for f in self.all_findings() if not f.fixed]),
        }
        if self.diff_findings or self.diff_review:
            out["diff_findings"] = [f.to_dict() for f in self.diff_findings]
            out["diff_review"] = self.diff_review
        return out

    def all_findings(self) -> list[CodeFinding]:
        return (
            list(self.review.findings)
            + list(self.static_findings)
            + list(self.macro_findings)
            + list(self.diff_findings)
        )


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
    elif area == "source" and ("macro" in title.lower() or "数据来源" in title or "audit" in title.lower()):
        memory.append(f"盘中审计：{title} — {detail[:160]}")
        policy.append("macro_ctx.sources 须含 flow/sentiment；缺失会触发 intraday_block_on_audit_fail")
        plan.append("补 collect_macro_context / enrich_macro_sources / portfolio sources_overrides")
    elif area == "diff" and finding.severity in ("critical", "high"):
        memory.append(f"diff review {finding.severity}：{title} — {detail[:160]}")
        plan.append(f"修复 diff：{title}")
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

    open_high = [
        f
        for f in findings
        if not f.fixed and f.severity in ("critical", "high")
    ]
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


def harness_evidence_findings(findings: list[CodeFinding]) -> list[CodeFinding]:
    """Findings eligible for harness memory — skip medium/low diff noise."""
    out: list[CodeFinding] = []
    for finding in findings:
        if finding.area == "diff" and finding.severity not in ("critical", "high"):
            continue
        out.append(finding)
    return out


def external_review_to_findings(items: list[dict[str, Any]]) -> list[CodeFinding]:
    """Bridge code-review-loop agent output into CodeFinding list."""
    out: list[CodeFinding] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sev = str(item.get("severity", "medium")).lower()
        if sev == "critical":
            sev = "high"
        location = str(item.get("location", "") or "")
        description = str(item.get("description", "") or item.get("title", "") or "")
        fix = str(item.get("suggested_fix", "") or "")
        detail = description
        if fix:
            detail = f"{description} | fix: {fix}"
        if location:
            detail = f"{location} — {detail}"
        out.append(
            CodeFinding(
                "diff",
                sev if sev in ("high", "medium", "low") else "medium",
                str(item.get("title") or description[:80] or "external review"),
                detail[:500],
            )
        )
    return out


def scan_macro_source_audit(
    portfolio: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> list[CodeFinding]:
    """Check daily cache macro_ctx.sources against data_audit categories (T10-style gaps)."""
    from agent_reach.daily_run.macro_collector import (
        enrich_macro_sources,
        macro_sources_complete,
        macro_sources_missing_raw,
        required_source_categories,
    )
    from agent_reach.daily_run.snapshot_cache import load_daily_cache

    cfg = settings or load_settings()
    pf = portfolio
    if pf is None:
        try:
            from agent_reach.daily_run.snapshot_builder import load_portfolio

            pf = load_portfolio()
        except FileNotFoundError:
            pf = {"holdings": [], "watchlist": [], "sources_overrides": {}}

    cache = load_daily_cache()
    macro_ctx = cache.get("macro_ctx") if isinstance(cache, dict) else {}
    if not isinstance(macro_ctx, dict):
        macro_ctx = {}
    raw_sources = macro_ctx.get("sources") if isinstance(macro_ctx.get("sources"), dict) else {}
    required = required_source_categories(cfg)
    macro_cats = [c for c in required if c != "quote"]
    findings: list[CodeFinding] = []

    if not cache:
        findings.append(
            CodeFinding(
                "source",
                "medium",
                "当日 macro 缓存缺失",
                "load_daily_cache() 为空；盘中可能重复 collect 或审计缺源",
            )
        )
        return findings

    if macro_sources_missing_raw(raw_sources, cfg):
        missing = [c for c in macro_cats if c not in set(raw_sources.keys())]
        findings.append(
            CodeFinding(
                "source",
                "medium",
                "macro 缓存 raw sources 不完整",
                f"缺少 raw 类别：{', '.join(missing) or 'unknown'}",
            )
        )

    enriched = enrich_macro_sources(pf, raw_sources, cfg)
    if not macro_sources_complete(enriched, pf, cfg):
        missing = []
        for cat in macro_cats:
            detail = enriched.get(cat)
            if not isinstance(detail, dict):
                missing.append(cat)
                continue
            summary = str(detail.get("summary", ""))
            if not summary or summary.startswith("("):
                missing.append(cat)
        findings.append(
            CodeFinding(
                "source",
                "high",
                "盘中数据来源审计未通过（macro_ctx.sources）",
                f"缺少数据来源类别：{', '.join(missing) or ', '.join(macro_cats)}",
            )
        )
    return findings


_DIFF_DAILY_RUN_PREFIX = "agent_reach/daily_run/"
_DIFF_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|secret|password|token)\s*=\s*['\"][^'\"]{8,}['\"]"
)
_DIFF_EVOLVED_READS = (
    '.get("macro_veto"',
    '.get("aggressive_entry"',
    '.get("holding_lock_days"',
    '.get("days_held")',
)
_DIFF_HELPERS = (
    "threshold_default",
    "effective_settings",
    "effective_days_held",
    "runtime_int_default",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git_diff_paths(
    *,
    base: str = "main",
    scope: str = "branch",
    repo_root: Optional[Path] = None,
) -> tuple[list[str], str]:
    root = repo_root or _repo_root()
    prefix = _DIFF_DAILY_RUN_PREFIX
    if scope == "uncommitted":
        cmd = ["git", "diff", "HEAD", "--name-only", "--", prefix]
    else:
        cmd = ["git", "diff", f"{base}...HEAD", "--name-only", "--", prefix]
    try:
        proc = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return [], ""
    if proc.returncode != 0:
        return [], (proc.stderr or proc.stdout or "").strip()
    paths = [p.strip() for p in (proc.stdout or "").splitlines() if p.strip()]
    return paths, ""


def _git_diff_text(
    *,
    base: str = "main",
    scope: str = "branch",
    repo_root: Optional[Path] = None,
) -> str:
    root = repo_root or _repo_root()
    prefix = _DIFF_DAILY_RUN_PREFIX
    if scope == "uncommitted":
        cmds = [
            ["git", "diff", "HEAD", "--", prefix],
            ["git", "diff", "--cached", "--", prefix],
        ]
    else:
        cmds = [["git", "diff", f"{base}...HEAD", "--", prefix]]
    chunks: list[str] = []
    for cmd in cmds:
        try:
            proc = subprocess.run(
                cmd,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if proc.returncode == 0 and proc.stdout:
            chunks.append(proc.stdout)
    return "\n".join(chunks)


def _parse_diff_added_lines(diff_text: str) -> dict[str, list[str]]:
    """Map file path → added line bodies from unified diff."""
    by_file: dict[str, list[str]] = {}
    current: Optional[str] = None
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:].strip()
            by_file.setdefault(current, [])
        elif line.startswith("+") and not line.startswith("+++"):
            if current:
                by_file.setdefault(current, []).append(line[1:])
    return by_file


def scan_diff_review(
    *,
    base: str = "main",
    scope: str = "branch",
    repo_root: Optional[Path] = None,
) -> tuple[list[CodeFinding], dict[str, Any]]:
    """Deterministic git-diff checks on agent_reach/daily_run/ (+ agent Phase R hints)."""
    root = repo_root or _repo_root()
    changed, git_err = _git_diff_paths(base=base, scope=scope, repo_root=root)
    meta: dict[str, Any] = {
        "base": base,
        "scope": scope,
        "changed_files": changed,
        "agent_phase": "R",
    }
    if git_err:
        meta["git_error"] = git_err
    if not changed:
        meta["skipped"] = True
        meta["reason"] = "no daily_run diff" if not git_err else "git diff failed"
        meta["agent_instructions"] = (
            "No agent_reach/daily_run/ diff — skip code-review-loop Diff/Domain agents "
            "or widen diff scope per user request."
        )
        return [], meta

    diff_text = _git_diff_text(base=base, scope=scope, repo_root=root)
    added_by_file = _parse_diff_added_lines(diff_text)
    findings: list[CodeFinding] = []
    py_changed = [p for p in changed if p.endswith(".py")]
    test_changed = any(p.startswith("tests/test_daily_run") for p in changed)

    for path in py_changed:
        added = added_by_file.get(path, [])
        blob = "\n".join(added)
        if not blob:
            continue
        if _DIFF_SECRET_RE.search(blob):
            findings.append(
                CodeFinding(
                    "diff",
                    "high",
                    f"{path} diff 可能含硬编码密钥",
                    "移除 secret/token；改用 env 或 settings",
                )
            )
        if "load_settings(" in blob and "effective_settings(" not in blob:
            findings.append(
                CodeFinding(
                    "diff",
                    "high",
                    f"{path} 新增 load_settings 未 overlay",
                    "消费者须 effective_settings() 后再读 thresholds/schedule",
                )
            )
        if any(r in blob for r in _DIFF_EVOLVED_READS) and not any(h in blob for h in _DIFF_HELPERS):
            findings.append(
                CodeFinding(
                    "diff",
                    "medium",
                    f"{path} diff 裸读 evolved 键",
                    "须 threshold_default / runtime_*_default / effective_days_held",
                )
            )
        if '.get("days_held")' in blob and "effective_days_held" not in blob:
            findings.append(
                CodeFinding(
                    "diff",
                    "medium",
                    f"{path} diff 直接读 days_held",
                    "业务判断应走 effective_days_held()",
                )
            )

    if py_changed and not test_changed:
        findings.append(
            CodeFinding(
                "diff",
                "medium",
                "daily_run 改动无对应 pytest diff",
                f"变更：{', '.join(py_changed[:5])}{'…' if len(py_changed) > 5 else ''}",
            )
        )

    open_high = [f for f in findings if f.severity in ("critical", "high")]
    meta["findings"] = len(findings)
    meta["open_high"] = len(open_high)
    meta["agent_instructions"] = (
        "Phase R: run code-review-loop Phase 2 in parallel — "
        "Diff Review + Holistic Review"
        + (" + Domain Review (daily_run changed)" if py_changed else "")
        + (" + Test Review (tests changed)" if test_changed else "")
        + f". Diff scope: {scope} vs {base}. "
        "Merge agent critical/high into harness via external_review_to_findings()."
    )
    return findings, meta


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

    all_findings = harness_evidence_findings(list(result.findings) + list(extra_findings or []))
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
    review_diff: bool = False,
    diff_base: str = "main",
    diff_scope: str = "branch",
) -> CodeWalkReport:
    """Full skill runtime: review + static scan + macro audit + optional diff + harness refine."""
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
    macro_findings = scan_macro_source_audit(portfolio, raw)
    diff_findings: list[CodeFinding] = []
    diff_review: dict[str, Any] = {}
    if review_diff:
        diff_findings, diff_review = scan_diff_review(base=diff_base, scope=diff_scope)

    existing_keys = {_finding_key(f) for f in review.findings}
    for finding in static_findings + macro_findings + diff_findings:
        if _finding_key(finding) not in existing_keys:
            review.findings.append(finding)
            existing_keys.add(_finding_key(finding))

    harness_refinement: dict[str, Any] = {}
    if evolve_harness:
        harness_refinement = apply_code_walk_harness_refinement(
            review,
            settings=cfg,
            extra_findings=static_findings + macro_findings + harness_evidence_findings(diff_findings),
        )
        review.harness_refinement = harness_refinement

    effective_after = effective_settings(raw)
    overlay = dict(effective_after.get("harness_runtime") or {})
    return CodeWalkReport(
        review=review,
        static_findings=static_findings,
        macro_findings=macro_findings,
        diff_findings=diff_findings,
        diff_review=diff_review,
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
    if report.macro_findings:
        lines.append("")
        lines.append("**Macro source audit**")
        for finding in report.macro_findings:
            lines.append(f"- [{finding.severity}] {finding.title}: {finding.detail}")
    if report.diff_findings or report.diff_review:
        lines.append("")
        lines.append("**Phase R — diff review**")
        dr = report.diff_review or {}
        if dr.get("changed_files"):
            lines.append(f"- scope: `{dr.get('scope', '')}` vs `{dr.get('base', 'main')}`")
            lines.append(f"- changed: {len(dr.get('changed_files', []))} files")
        for finding in report.diff_findings:
            lines.append(f"- [{finding.severity}] {finding.title}: {finding.detail}")
        if dr.get("agent_instructions"):
            lines.append("")
            lines.append(f"_Agent: {dr['agent_instructions']}_")
    if report.effective_overlay.get("threshold_overlay"):
        lines.append("")
        lines.append("**Effective overlay 快照**")
        lines.append("```json")
        lines.append(json.dumps(report.effective_overlay, ensure_ascii=False, indent=2))
        lines.append("```")
    open_high = [
        f
        for f in report.review.findings
        if not f.fixed and f.severity in ("critical", "high")
    ]
    if open_high:
        lines.append("")
        lines.append("**Phase G — Grill 追问（open high）**")
        lines.append(
            f"- {len(open_high)} 条待关闭；按 daily-run-code-walk skill "
            "Phase G 逐条 AskUserQuestion → Bug Fix Plan 后再改代码"
        )
        lines.append("- 参考：`.cursor/skills/daily-run-code-walk/references/grill-me-bug-fix.md`")
        for finding in open_high[:8]:
            lines.append(f"- [{finding.severity}] {finding.area} · {finding.title}")
    return "\n".join(lines).strip() + "\n"

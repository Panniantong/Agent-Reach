# -*- coding: utf-8
"""Close review code walkthrough — detect runtime/config bugs and apply safe fixes."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.portfolio_manager import (
    max_total_symbols,
    unique_symbol_codes,
    unique_symbol_count,
    watchlist_capacity,
)
from agent_reach.daily_run.snapshot_builder import _normalize_code
from agent_reach.daily_run.symbols import copy_portfolio

DEFAULT_WALK_MODULES = (
    "portfolio_manager.py",
    "watchlist_manager.py",
    "intraday.py",
    "schedule.py",
    "workflows.py",
    "close_improvements.py",
    "close_code_review.py",
    "snapshot_builder.py",
    "verify.py",
)


@dataclass
class CodeFinding:
    area: str  # portfolio | intraday | manifest | source
    severity: str  # high | medium | low
    title: str
    detail: str
    fixed: bool = False
    fix_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "area": self.area,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "fixed": self.fixed,
            "fix_note": self.fix_note,
        }


@dataclass
class CodeReviewResult:
    findings: list[CodeFinding] = field(default_factory=list)
    fixes_applied: list[str] = field(default_factory=list)
    portfolio: Optional[dict[str, Any]] = None
    portfolio_changed: bool = False
    smoke_tests: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "fixes_applied": self.fixes_applied,
            "portfolio_changed": self.portfolio_changed,
            "smoke_tests": self.smoke_tests,
        }


def run_close_code_review(
    *,
    portfolio: dict[str, Any],
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    scans: Optional[list[dict[str, Any]]] = None,
    trades: Optional[list[dict[str, Any]]] = None,
) -> CodeReviewResult:
    """Walk through daily-run state + source modules; repair portfolio when safe."""
    cfg = settings.get("close_code_review") or {}
    if cfg.get("enabled") is False:
        return CodeReviewResult(portfolio=portfolio)

    out = CodeReviewResult(portfolio=copy_portfolio(portfolio))
    auto_fix = cfg.get("auto_fix_portfolio", True) is not False

    _review_portfolio(out, snapshot, settings, auto_fix=auto_fix)
    _review_intraday_state(out, scans or [], trades or [], settings)
    _review_today_manifests(out)
    if cfg.get("walk_on_close", False) is True:
        _walk_source_modules(out, settings)

    if cfg.get("run_smoke_tests") is True:
        out.smoke_tests = _run_smoke_tests(settings)

    return out


def render_code_review_markdown(result: CodeReviewResult, *, enabled: bool = True) -> str:
    if not enabled:
        return ""
    lines = ["**🩺 代码走读与 Bug 修复**", ""]
    if result.fixes_applied:
        lines.append("**已自动修复：**")
        for fix in result.fixes_applied:
            lines.append(f"- ✅ {fix}")
        lines.append("")

    open_findings = [f for f in result.findings if not f.fixed]
    if open_findings:
        lines.append("**待处理：**")
        for f in open_findings:
            badge = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(f.severity, "•")
            lines.append(f"- {badge} [{f.area}] **{f.title}** — {f.detail}")
        lines.append("")

    if result.smoke_tests:
        st = result.smoke_tests
        if st.get("ok"):
            lines.append(f"**冒烟测试：** {st.get('passed', 0)} passed")
        else:
            lines.append(f"**冒烟测试失败：** {st.get('summary', '见日志')}")
        lines.append("")

    if not result.fixes_applied and not open_findings and not (
        result.smoke_tests and not result.smoke_tests.get("ok")
    ):
        lines.append("走读未发现运行时或源码级缺陷，portfolio / intraday 状态一致。")

    return "\n".join(lines).strip()


def _live_price_for_code(snapshot: dict[str, Any], code: str) -> Optional[float]:
    """Best-effort live price from close snapshot holdings/watchlist rows."""
    norm = _normalize_code(code)
    for block in (
        (snapshot.get("portfolio") or {}).get("holdings") or [],
        snapshot.get("watchlist") or [],
    ):
        for row in block:
            if _normalize_code(str(row.get("code", ""))) != norm:
                continue
            if row.get("quote_source") == "cost_fallback":
                continue
            price = row.get("price")
            if price is not None:
                try:
                    return float(price)
                except (TypeError, ValueError):
                    return None
    if _normalize_code(str(snapshot.get("code", ""))) == norm:
        price = snapshot.get("price")
        if price is not None:
            try:
                return float(price)
            except (TypeError, ValueError):
                return None
    return None


def _review_portfolio(
    out: CodeReviewResult,
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    *,
    auto_fix: bool,
) -> None:
    pf = out.portfolio or {}
    holdings = list(pf.get("holdings") or [])
    watchlist = list(pf.get("watchlist") or [])
    held = {
        _normalize_code(str(h.get("code", "")))
        for h in holdings
        if _normalize_code(str(h.get("code", "")))
    }
    max_t = max_total_symbols(settings)

    overlap = [
        w
        for w in watchlist
        if _normalize_code(str(w.get("code", ""))) in held
    ]
    if overlap:
        names = "、".join(str(w.get("name", w.get("code"))) for w in overlap[:3])
        if auto_fix:
            wl = [
                w
                for w in watchlist
                if _normalize_code(str(w.get("code", ""))) not in held
            ]
            pf["watchlist"] = wl
            out.portfolio = pf
            out.portfolio_changed = True
            msg = f"已从观察池移除与持仓重复的 {len(overlap)} 只（{names}）"
            out.fixes_applied.append(msg)
            out.findings.append(
                CodeFinding(
                    "portfolio",
                    "medium",
                    "观察池与持仓重复",
                    names,
                    fixed=True,
                    fix_note=msg,
                )
            )
            watchlist = wl
        else:
            out.findings.append(
                CodeFinding(
                    "portfolio",
                    "medium",
                    "观察池与持仓重复",
                    f"{len(overlap)} 只：{names}；建议收盘 adjust_watchlist 或启用 auto_fix",
                )
            )

    unique_n = unique_symbol_count(pf)
    if unique_n > max_t:
        cap = watchlist_capacity(settings, pf)
        if auto_fix and len(watchlist) > cap:
            trimmed = _trim_watchlist_by_snapshot(watchlist, held, snapshot, cap)
            removed = len(watchlist) - len(trimmed)
            pf["watchlist"] = trimmed
            out.portfolio = pf
            out.portfolio_changed = True
            msg = f"观察池 trim {removed} 只，合计 {unique_n}→{unique_symbol_count(pf)}（上限 {max_t}）"
            out.fixes_applied.append(msg)
            out.findings.append(
                CodeFinding(
                    "portfolio",
                    "high",
                    "持仓+观察池超出合计上限",
                    f"原 {unique_n} 只 > {max_t}",
                    fixed=True,
                    fix_note=msg,
                )
            )
        else:
            out.findings.append(
                CodeFinding(
                    "portfolio",
                    "high",
                    "持仓+观察池超出合计上限",
                    f"合计 {unique_n} 只 > {max_t}；需手动卖出或移出观察池",
                )
            )

    for h in holdings:
        code = _normalize_code(str(h.get("code", "")))
        shares = int(h.get("shares") or 0)
        if shares <= 0:
            out.findings.append(
                CodeFinding(
                    "portfolio",
                    "high",
                    f"持仓 {code} 股数无效",
                    f"shares={h.get('shares')}；需人工核对 portfolio.json",
                )
            )
        cost = h.get("cost")
        live_price = _live_price_for_code(snapshot, code)
        if (
            auto_fix
            and cost is not None
            and live_price is not None
            and float(cost) > float(live_price) * 2.5
        ):
            old_cost = float(cost)
            h["cost"] = round(float(live_price), 4)
            pf["holdings"] = holdings
            out.portfolio = pf
            out.portfolio_changed = True
            msg = f"持仓 {code} cost {old_cost} → {live_price}（与市价偏差过大，已按 snapshot 修正）"
            out.fixes_applied.append(msg)
            out.findings.append(
                CodeFinding(
                    "portfolio",
                    "high",
                    f"持仓 {code} 成本价异常",
                    f"cost={old_cost} vs 市价 {live_price}",
                    fixed=True,
                    fix_note=msg,
                )
            )
        if h.get("days_held") is None:
            out.findings.append(
                CodeFinding(
                    "portfolio",
                    "low",
                    f"持仓 {code} 缺少 days_held",
                    "早盘 increment_holding_days 可能未执行",
                )
            )

    cash = pf.get("cash")
    total = pf.get("total")
    ratio = pf.get("cash_ratio")
    if cash is not None and total is not None and float(total) > 0 and ratio is not None:
        expected = round(float(cash) / float(total), 4)
        if abs(expected - float(ratio)) > 0.02:
            detail = f"记录 {float(ratio):.2%} vs 计算 {expected:.2%}"
            if auto_fix:
                pf["cash_ratio"] = expected
                out.portfolio = pf
                out.portfolio_changed = True
                msg = f"已重算 cash_ratio：{detail}"
                out.fixes_applied.append(msg)
                out.findings.append(
                    CodeFinding(
                        "portfolio",
                        "medium",
                        "cash_ratio 与 cash/total 不一致",
                        detail,
                        fixed=True,
                        fix_note=msg,
                    )
                )
            else:
                out.findings.append(
                    CodeFinding(
                        "portfolio",
                        "medium",
                        "cash_ratio 与 cash/total 不一致",
                        detail,
                    )
                )


def _review_intraday_state(
    out: CodeReviewResult,
    scans: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    settings: dict[str, Any],
) -> None:
    from agent_reach.daily_run.intraday import MAX_SCANS, MAX_TRADES

    if not scans and not trades:
        return

    ids = [s.get("scan_id") for s in scans if s.get("scan_id")]
    if len(ids) != len(set(ids)):
        out.findings.append(
            CodeFinding(
                "intraday",
                "high",
                "S_n scan_id 重复",
                "intraday_state.json 存在重复 scan_id，Lookback MSS 可能失真",
            )
        )

    if len(scans) > MAX_SCANS:
        out.findings.append(
            CodeFinding(
                "intraday",
                "medium",
                f"扫描次数 {len(scans)} 超过 MAX_SCANS={MAX_SCANS}",
                "检查 schedule 是否重复触发或 state 未按日重置",
            )
        )

    if len(trades) > MAX_TRADES:
        out.findings.append(
            CodeFinding(
                "intraday",
                "medium",
                f"调仓次数 {len(trades)} 超过 MAX_TRADES={MAX_TRADES}",
                "检查 trade_every_n_scans 配置",
            )
        )

    s2 = next((s for s in scans if s.get("scan_id") == "S2"), None)
    if s2 and s2.get("source") != "morning":
        out.findings.append(
            CodeFinding(
                "intraday",
                "medium",
                "S2 未标记 morning 来源",
                "08:00 早盘应写入 record_morning_scan(source=morning)",
            )
        )

    expected_ids = {f"S{i}" for i in range(1, MAX_SCANS + 1)}
    if ids:
        missing = sorted(expected_ids - set(ids))
        if missing and len(scans) >= 2:
            out.findings.append(
                CodeFinding(
                    "intraday",
                    "low",
                    "S_n 序列存在空档",
                    f"缺失：{', '.join(missing[:6])}{'…' if len(missing) > 6 else ''}",
                )
            )


def _review_today_manifests(out: CodeReviewResult) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    runs_dir = Path.home() / ".agent-reach" / "daily_run" / "runs" / today
    if not runs_dir.is_dir():
        out.findings.append(
            CodeFinding(
                "manifest",
                "low",
                "今日无 run manifest",
                f"{runs_dir} 不存在；GHA artifact 或未写入 runs/",
            )
        )
        return

    for path in sorted(runs_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            out.findings.append(
                CodeFinding(
                    "manifest",
                    "high",
                    f"manifest 损坏：{path.name}",
                    str(exc),
                )
            )
            continue

        feishu = record.get("feishu") or {}
        if isinstance(feishu, dict) and feishu.get("code") not in (None, 0):
            out.findings.append(
                CodeFinding(
                    "manifest",
                    "high",
                    f"飞书推送失败（{path.stem}）",
                    feishu.get("msg") or str(feishu.get("code")),
                )
            )

        payload = record.get("payload") or {}
        job = payload.get("job") or record.get("job")
        inner = (payload.get("result") or {}) if isinstance(payload.get("result"), dict) else {}
        if job == "close" and inner and "improvements" not in inner:
            out.findings.append(
                CodeFinding(
                    "manifest",
                    "medium",
                    "close manifest 缺少 improvements",
                    "可能运行了旧版代码；确认 GHA checkout 为 main 最新",
                )
            )


def _walk_source_modules(out: CodeReviewResult, settings: dict[str, Any]) -> None:
    cfg = settings.get("close_code_review") or {}
    names = cfg.get("walk_modules") or list(DEFAULT_WALK_MODULES)
    try:
        import agent_reach.daily_run as pkg

        base = Path(pkg.__file__).resolve().parent
    except (ImportError, TypeError):
        out.findings.append(
            CodeFinding("source", "low", "无法定位 daily_run 源码", "跳过 AST 走读")
        )
        return

    for name in names:
        path = base / name
        if not path.is_file():
            out.findings.append(
                CodeFinding("source", "low", f"模块缺失：{name}", str(path))
            )
            continue
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            out.findings.append(
                CodeFinding(
                    "source",
                    "high",
                    f"语法错误：{name}",
                    f"line {exc.lineno}: {exc.msg}",
                )
            )
            continue

        _check_bare_except(out, tree, name)
        _check_undefined_name_patterns(out, source, name)


def _check_bare_except(out: CodeReviewResult, tree: ast.AST, module: str) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            out.findings.append(
                CodeFinding(
                    "source",
                    "low",
                    f"{module} 存在 bare except",
                    f"line {node.lineno}：建议捕获具体异常类型",
                )
            )


def _check_undefined_name_patterns(out: CodeReviewResult, source: str, module: str) -> None:
    # Heuristic: NameError-prone patterns seen in production
    if "if len(weak)" in source and "weak = " not in source:
        out.findings.append(
            CodeFinding(
                "source",
                "high",
                f"{module} 可能引用未定义 weak",
                "close_improvements 类 bug：使用前需定义 weak 列表",
            )
        )


def _run_smoke_tests(settings: dict[str, Any]) -> dict[str, Any]:
    cfg = settings.get("close_code_review") or {}
    patterns = cfg.get("smoke_test_globs") or [
        "tests/test_daily_run_portfolio_manager.py",
        "tests/test_daily_run_watchlist_manager.py",
        "tests/test_daily_run_close_improvements.py",
    ]
    repo = Path(__file__).resolve().parents[2]
    args = [sys.executable, "-m", "pytest", *patterns, "-q", "--tb=no"]
    try:
        proc = subprocess.run(
            args,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=120,
        )
        summary = (proc.stdout or proc.stderr or "").strip().splitlines()[-1:] or [""]
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "summary": summary[0],
            "passed": _parse_pytest_passed(summary[0]),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "summary": "pytest 超时（120s）"}
    except OSError as exc:
        return {"ok": False, "summary": str(exc)}


def _parse_pytest_passed(line: str) -> int:
    if " passed" in line:
        try:
            return int(line.split(" passed")[0].split()[-1])
        except (ValueError, IndexError):
            pass
    return 0


def _trim_watchlist_by_snapshot(
    watchlist: list[dict[str, Any]],
    held: set[str],
    snapshot: dict[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    wl = [w for w in watchlist if _normalize_code(str(w.get("code", ""))) not in held]
    if len(wl) <= limit:
        return wl

    def score(w: dict[str, Any]) -> float:
        code = _normalize_code(str(w.get("code", "")))
        for src in (snapshot.get("watchlist") or []):
            if _normalize_code(str(src.get("code", ""))) == code:
                chg = src.get("change_pct")
                base = float(snapshot.get("mss_final") or 50)
                return base + (float(chg) * 0.5 if chg is not None else 0)
        return 50.0

    ranked = sorted(wl, key=score, reverse=True)
    return ranked[:limit]

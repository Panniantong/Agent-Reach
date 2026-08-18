# -*- coding: utf-8 -*-
"""Intraday scan (S1-S15) and trade (T1-T5) workflow with lookback MSS."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.lookback import compute_lookback_mss, detect_mss_trend
from agent_reach.daily_run.pipeline import evaluate_snapshot, render_markdown
from agent_reach.daily_run.plugins.loader import run_experts
from agent_reach.daily_run.harness_policy import (
    friction_min_return_default,
    aggressive_entry_default,
    macro_veto_default,
    min_cash_ratio_default,
    runtime_int_default,
)
from agent_reach.daily_run.settings import effective_settings, load_settings
from agent_reach.daily_run.trade_calendar import today_shanghai


from agent_reach.daily_run.schedule import INTRADAY_MAX_SCANS as MAX_SCANS

MAX_TRADES = 5  # legacy alias; prefer max_applied_trades_per_day / max_trade_evaluations_per_symbol


def max_applied_trades_per_day(settings: Optional[dict[str, Any]] = None) -> int:
    cfg = effective_settings(settings or load_settings())
    return max(1, runtime_int_default(cfg, "schedule", "max_applied_trades_per_day"))


def max_trade_evaluations_per_symbol(settings: Optional[dict[str, Any]] = None) -> int:
    cfg = effective_settings(settings or load_settings())
    return max(1, runtime_int_default(cfg, "schedule", "max_trade_evaluations_per_symbol"))


def append_trade_skip_note(markdown: str, reason: str) -> str:
    text = str(reason or "").strip()
    if not text:
        return markdown
    note = f"⚠️ **本轮未调仓评估：** {text}"
    if not markdown.strip():
        return note
    return markdown.rstrip() + "\n\n" + note


def explain_trade_skip_reason(
    state: Optional[IntradayState] = None,
    settings: Optional[dict[str, Any]] = None,
    *,
    state_path: Optional[Path] = None,
) -> str:
    """Human-readable reason when should_evaluate_trade is False."""
    cfg = effective_settings(settings or load_settings())
    sched = cfg.get("schedule") or {}
    if sched.get("intraday_trade_enabled", True) is not True:
        return "盘中调仓已关闭（schedule.intraday_trade_enabled=false）"

    st = state or load_state(state_path)
    min_scans = runtime_int_default(cfg, "schedule", "trade_min_scans")
    if len(st.scans) < min_scans:
        return f"扫描次数不足（需 ≥{min_scans} 次，当前 {len(st.scans)} 次）"

    eval_cap = max_trade_evaluations_per_symbol(cfg)
    if len(st.trades) >= eval_cap:
        return f"本标的调仓评估已达上限 T1–T{eval_cap}（含 hold 记录）"

    trend = detect_mss_trend(st.scans)
    every_n = runtime_int_default(cfg, "schedule", "trade_every_n_scans")
    if trend in ("turning_up", "turning_down", "rising", "falling"):
        return "内部状态异常：趋势已变化但未触发评估"

    return (
        f"未命中调仓评估节奏（趋势 {trend}，每 {every_n} 次扫描评估一次；"
        f"当前 S{len(st.scans)}）"
    )


@dataclass
class TradeDecision:
    action: str  # buy | sell | hold | skip
    trade_id: Optional[str]
    lookback_mss: float
    lookback_detail: list[dict[str, Any]]
    trend: str
    reasoning: str
    blocked: bool = False
    friction_blocked: bool = False
    expected_return_pct: Optional[float] = None
    evaluation: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "trade_id": self.trade_id,
            "lookback_mss": self.lookback_mss,
            "lookback_detail": self.lookback_detail,
            "trend": self.trend,
            "reasoning": self.reasoning,
            "blocked": self.blocked,
            "friction_blocked": self.friction_blocked,
            "expected_return_pct": self.expected_return_pct,
        }


@dataclass
class IntradayState:
    date: str
    scans: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"date": self.date, "scans": self.scans, "trades": self.trades}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntradayState:
        return cls(
            date=str(data.get("date", _today_str())),
            scans=list(data.get("scans") or []),
            trades=list(data.get("trades") or []),
        )


def default_state_path(code: Optional[str] = None) -> Path:
    if code:
        from agent_reach.daily_run.snapshot_builder import _normalize_code

        norm = _normalize_code(str(code))
        return Path.home() / ".agent-reach" / "daily_run" / "intraday" / f"{norm}.json"
    return Path.home() / ".agent-reach" / "daily_run" / "intraday_state.json"


def load_state(path: Optional[Path] = None, *, code: Optional[str] = None) -> IntradayState:
    p = path or default_state_path(code)
    if not p.exists():
        return IntradayState(date=_today_str())
    data = json.loads(p.read_text(encoding="utf-8"))
    state = IntradayState.from_dict(data)
    if state.date != _today_str():
        return IntradayState(date=_today_str())
    return state


def save_state(state: IntradayState, path: Optional[Path] = None) -> Path:
    p = path or default_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n"
    tmp = p.with_suffix(".tmp")
    try:
        import fcntl

        lock_file = p.parent / ".intraday.lock"
        with open(lock_file, "w", encoding="utf-8") as lockf:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(p)
    except (ImportError, OSError):
        p.write_text(payload, encoding="utf-8")
    return p


def reset_state(path: Optional[Path] = None) -> IntradayState:
    state = IntradayState(date=_today_str())
    save_state(state, path)
    return state


def record_scan(
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    doctor_channels: Optional[dict[str, dict]] = None,
    plugin_names: Optional[list[str]] = None,
    state: Optional[IntradayState] = None,
    state_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Record one intraday data collection (S_n) after experts + evaluate."""
    cfg = effective_settings(settings)
    st = state or load_state(state_path)

    if len(st.scans) >= MAX_SCANS:
        raise RuntimeError(f"今日扫描已达上限 {MAX_SCANS} 次（S1-S{MAX_SCANS}）")

    enriched = dict(snapshot)
    enriched.setdefault("report_type", "intraday")
    enriched.setdefault("as_of", datetime.now(timezone.utc).isoformat())

    from agent_reach.daily_run.team import experts_enabled, mss_experts_enabled

    if experts_enabled(cfg, workflow="intraday"):
        enriched = run_experts(dict(snapshot), cfg, names=plugin_names)
        enriched.setdefault("report_type", "intraday")
        enriched.setdefault("as_of", datetime.now(timezone.utc).isoformat())
    elif mss_experts_enabled(cfg, workflow="intraday"):
        from agent_reach.daily_run.plugins.loader import MSS_EXPERT_NAMES, run_experts

        enriched = run_experts(dict(snapshot), cfg, names=MSS_EXPERT_NAMES)
        enriched.setdefault("report_type", "intraday")
        enriched.setdefault("as_of", datetime.now(timezone.utc).isoformat())

    evaluation = evaluate_snapshot(enriched, cfg, doctor_channels=doctor_channels)
    report = evaluation["report"]
    scan_id = f"S{len(st.scans) + 1}"

    entry = {
        "scan_id": scan_id,
        "as_of": report.get("as_of"),
        "code": report.get("code"),
        "name": report.get("name"),
        "mss_final": report.get("mss_final"),
        "mss_breakdown": report.get("mss_breakdown"),
        "verdict": report.get("verdict"),
        "confidence": report.get("confidence"),
        "price": enriched.get("price"),
        "audit_passed": evaluation["audit"].passed,
    }
    st.scans.append(entry)
    save_state(st, state_path)

    lookback_mss, lookback_detail = compute_lookback_mss(st.scans, cfg)
    trend = detect_mss_trend(st.scans)

    return {
        "scan": entry,
        "enriched": enriched,
        "state": st.to_dict(),
        "evaluation": evaluation,
        "lookback_mss": lookback_mss,
        "lookback_detail": lookback_detail,
        "trend": trend,
        "markdown": render_intraday_scan_markdown(
            entry, lookback_mss, lookback_detail, trend, report, scan_count=len(st.scans)
        ),
    }


def record_morning_scan(
    run_result: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    code: Optional[str] = None,
    state_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Record 08:00 morning analysis as S1 in intraday state."""
    evaluation = run_result.get("evaluation")
    if not evaluation:
        raise ValueError("run_result missing evaluation for morning S1 scan")
    enriched = run_result.get("snapshot") or {}
    return record_scan_from_evaluation(
        enriched,
        evaluation,
        settings=settings,
        state_path=state_path,
        code=code,
        source="morning",
    )


def record_scan_from_evaluation(
    enriched: dict[str, Any],
    evaluation: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    state: Optional[IntradayState] = None,
    state_path: Optional[Path] = None,
    source: Optional[str] = None,
    code: Optional[str] = None,
) -> dict[str, Any]:
    """Append S_n from an existing evaluation (morning S1 backfill)."""
    cfg = settings or load_settings()
    sym = code or enriched.get("code")
    resolved_path = state_path or (default_state_path(sym) if sym else default_state_path())
    st = state or load_state(resolved_path, code=sym)

    if len(st.scans) >= MAX_SCANS:
        raise RuntimeError(f"今日扫描已达上限 {MAX_SCANS} 次（S1-S{MAX_SCANS}）")

    report = evaluation["report"]
    scan_id = f"S{len(st.scans) + 1}"

    entry = {
        "scan_id": scan_id,
        "as_of": report.get("as_of"),
        "code": report.get("code"),
        "name": report.get("name"),
        "mss_final": report.get("mss_final"),
        "mss_breakdown": report.get("mss_breakdown"),
        "verdict": report.get("verdict"),
        "confidence": report.get("confidence"),
        "price": enriched.get("price"),
        "audit_passed": evaluation["audit"].passed,
    }
    if source:
        entry["source"] = source
    st.scans.append(entry)
    save_state(st, resolved_path)

    lookback_mss, lookback_detail = compute_lookback_mss(st.scans, cfg)
    trend = detect_mss_trend(st.scans)

    return {
        "scan": entry,
        "state": st.to_dict(),
        "lookback_mss": lookback_mss,
        "lookback_detail": lookback_detail,
        "trend": trend,
        "markdown": render_intraday_scan_markdown(
            entry, lookback_mss, lookback_detail, trend, report, scan_count=len(st.scans)
        ),
    }


def should_evaluate_trade(
    state: Optional[IntradayState] = None,
    settings: Optional[dict[str, Any]] = None,
    *,
    state_path: Optional[Path] = None,
) -> bool:
    """Heuristic: trade after ≥ trade_min_scans scans, on trend shift or every N scans."""
    cfg = effective_settings(settings)
    sched = cfg.get("schedule", {})
    if not sched.get("intraday_trade_enabled", True):
        return False

    st = state or load_state(state_path)
    if len(st.scans) < runtime_int_default(cfg, "schedule", "trade_min_scans"):
        return False
    if len(st.trades) >= max_trade_evaluations_per_symbol(cfg):
        return False

    trend = detect_mss_trend(st.scans)
    if trend in ("turning_up", "turning_down", "rising", "falling"):
        return True
    every_n = runtime_int_default(cfg, "schedule", "trade_every_n_scans")
    return len(st.scans) % every_n == 0


def apply_paper_trade(
    decision: TradeDecision,
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> "ApplyResult":
    """Apply paper buy/sell to portfolio.json when auto_adjust is enabled."""
    from agent_reach.daily_run.portfolio_manager import (
        ApplyResult,
        append_trade_ledger,
        apply_auto_adjust,
        global_trades_today,
        is_auto_adjust_enabled,
        register_applied_trade,
    )
    from agent_reach.daily_run.snapshot_builder import load_portfolio, save_portfolio
    from agent_reach.daily_run.symbols import sync_snapshot_portfolio

    cfg = effective_settings(settings)
    pf = load_portfolio()
    if not is_auto_adjust_enabled(cfg):
        return ApplyResult(applied=False, portfolio=pf, message="auto_adjust 未启用")

    from agent_reach.daily_run.snapshot_builder import _normalize_code
    from agent_reach.daily_run.symbols import build_enriched_symbols

    quote_map = build_enriched_symbols(snapshot)
    snap = dict(snapshot)
    sync_snapshot_portfolio(snap, pf)
    for row in (snap.get("portfolio") or {}).get("holdings") or []:
        code = _normalize_code(str(row.get("code", "")))
        if code in quote_map:
            row.update({k: quote_map[code][k] for k in ("price", "change_pct", "name", "ma20") if quote_map[code].get(k) is not None})
    merged_watchlist = []
    for row in snap.get("watchlist") or []:
        item = dict(row)
        code = _normalize_code(str(item.get("code", "")))
        if code in quote_map:
            item.update({k: quote_map[code][k] for k in ("price", "change_pct", "name", "ma20") if quote_map[code].get(k) is not None})
        merged_watchlist.append(item)
    snap["watchlist"] = merged_watchlist

    action = decision.action
    applied_cap = max_applied_trades_per_day(cfg)
    if action in ("buy", "sell") and global_trades_today() >= applied_cap:
        return ApplyResult(
            applied=False,
            portfolio=pf,
            message=(
                f"今日全组合落账已达上限 {applied_cap} 次，"
                f"{'买入' if action == 'buy' else '卖出'}信号仅记录不落账"
            ),
        )

    result = apply_auto_adjust(pf, decision, snap, cfg, allow_watchlist_changes=False)
    if result.applied:
        if not register_applied_trade(result.actions):
            pf_now = load_portfolio()
            return ApplyResult(
                applied=False,
                portfolio=pf_now,
                message="重复成交已忽略（同日相同指令）",
            )
        save_portfolio(result.portfolio)
        sync_snapshot_portfolio(snap, result.portfolio)
        append_trade_ledger(
            result.actions,
            trade_id=decision.trade_id,
            decision_action=decision.action,
        )
    return result


def evaluate_trade(
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    doctor_channels: Optional[dict[str, dict]] = None,
    plugin_names: Optional[list[str]] = None,
    state: Optional[IntradayState] = None,
    state_path: Optional[Path] = None,
    expected_return_pct: Optional[float] = None,
    pre_enriched: Optional[dict[str, Any]] = None,
    pre_evaluation: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Evaluate T_n trade opportunity using lookback MSS over recent scans."""
    cfg = effective_settings(settings)
    st = state or load_state(state_path)

    eval_cap = max_trade_evaluations_per_symbol(cfg)
    if len(st.trades) >= eval_cap:
        raise RuntimeError(
            f"今日调仓评估已达上限 {eval_cap} 次（T1-T{eval_cap}）"
        )
    if not st.scans:
        raise RuntimeError("尚无扫描记录，请先运行 daily-run intraday scan")

    if pre_enriched is not None and pre_evaluation is not None:
        enriched = pre_enriched
        evaluation = pre_evaluation
    else:
        from agent_reach.daily_run.team import experts_enabled, mss_experts_enabled

        if experts_enabled(cfg, workflow="intraday"):
            enriched = run_experts(dict(snapshot), cfg, names=plugin_names)
        elif mss_experts_enabled(cfg, workflow="intraday"):
            from agent_reach.daily_run.plugins.loader import MSS_EXPERT_NAMES, run_experts

            enriched = run_experts(dict(snapshot), cfg, names=MSS_EXPERT_NAMES)
        else:
            enriched = dict(snapshot)
        enriched.setdefault("report_type", "intraday")
        evaluation = evaluate_snapshot(enriched, cfg, doctor_channels=doctor_channels)

    report = evaluation["report"]
    verdict = evaluation["verdict"]

    lookback_mss, lookback_detail = compute_lookback_mss(st.scans, cfg)
    trend = detect_mss_trend(st.scans)
    decision = _decide_trade(
        lookback_mss=lookback_mss,
        trend=trend,
        verdict=verdict,
        report=report,
        snapshot=enriched,
        settings=cfg,
        trade_index=len(st.trades) + 1,
        expected_return_pct=expected_return_pct,
    )

    trade_record = {
        **decision.to_dict(),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "verdict": report.get("verdict"),
        "mss_final": report.get("mss_final"),
        "code": report.get("code"),
        "name": report.get("name"),
    }
    apply_result = apply_paper_trade(decision, enriched, settings=cfg)
    trade_record["portfolio_applied"] = apply_result.applied
    trade_record["portfolio_message"] = apply_result.message
    if apply_result.applied:
        trade_record["portfolio_actions"] = [a.to_dict() for a in apply_result.actions]
    st.trades.append(trade_record)
    save_state(st, state_path)

    from agent_reach.daily_run.portfolio_manager import render_apply_markdown

    markdown = render_intraday_trade_markdown(decision, lookback_detail, report, st.scans)
    markdown = markdown + "\n\n---\n\n" + render_apply_markdown(apply_result)

    return {
        "decision": decision.to_dict(),
        "trade": trade_record,
        "state": st.to_dict(),
        "evaluation": evaluation,
        "portfolio_apply": apply_result.to_dict(),
        "markdown": markdown,
    }


def run_intraday(
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    doctor_channels: Optional[dict[str, dict]] = None,
    plugin_names: Optional[list[str]] = None,
    push: bool = True,
    trade: bool = False,
    title: Optional[str] = None,
    config=None,
    expected_return_pct: Optional[float] = None,
    state_path: Optional[Path] = None,
) -> dict[str, Any]:
    """One-click intraday: record scan → optional trade eval → Feishu push."""
    cfg = effective_settings(settings)
    steps: list[str] = []

    scan_result = record_scan(
        snapshot,
        settings=cfg,
        doctor_channels=doctor_channels,
        plugin_names=plugin_names,
        state_path=state_path,
    )
    steps.append("scan")

    st_after_scan = IntradayState.from_dict(scan_result["state"])
    do_trade = trade or should_evaluate_trade(st_after_scan, cfg, state_path=state_path)
    if not do_trade:
        skip_reason = explain_trade_skip_reason(st_after_scan, cfg, state_path=state_path)
        scan_result["markdown"] = append_trade_skip_note(scan_result.get("markdown") or "", skip_reason)
        scan_result["trade_skip_reason"] = skip_reason

    trade_result = None
    if do_trade and not trade:
        steps.append("trade_auto")

    if do_trade:
        trade_result = evaluate_trade(
            scan_result.get("enriched") or snapshot,
            settings=cfg,
            doctor_channels=doctor_channels,
            plugin_names=plugin_names,
            state=IntradayState.from_dict(scan_result["state"]),
            state_path=state_path,
            expected_return_pct=expected_return_pct,
            pre_enriched=scan_result.get("enriched"),
            pre_evaluation=scan_result.get("evaluation"),
        )
        steps.append("trade")
        if trade_result.get("portfolio_apply", {}).get("applied"):
            steps.append("portfolio_apply")

    feishu_result = None
    push_error: Optional[str] = None
    if push:
        from agent_reach.config import Config
        from agent_reach.integrations.feishu import FeishuError, send_card

        cfg_obj = config or Config()
        tpl = cfg.get("report", {}).get("feishu_template_intraday", "blue")
        scan_id = scan_result["scan"]["scan_id"]
        name = scan_result["scan"].get("name") or scan_result["scan"].get("code") or "大盘"
        card_title = title or f"📊 盘中 {scan_id} · {name}"

        md_parts = [scan_result["markdown"]]
        audit = (scan_result.get("evaluation") or {}).get("audit")
        if audit and (audit.warnings or not audit.passed):
            warn_lines = ["**⚠️ 数据审计提示**"]
            if not audit.passed:
                warn_lines.append("；".join(audit.issues))
            for w in audit.warnings:
                warn_lines.append(f"- {w}")
            md_parts.insert(0, "\n".join(warn_lines) + "\n\n---\n\n")
        if trade_result:
            md_parts.append("\n---\n\n" + trade_result["markdown"])
        try:
            feishu_result = send_card(cfg_obj, card_title, "\n".join(md_parts), template=tpl)
            steps.append("push")
        except FeishuError as exc:
            push_error = str(exc)

    out: dict[str, Any] = {
        "steps": steps,
        "scan": scan_result,
        "trade": trade_result,
        "feishu": feishu_result,
        "scan_count": len(scan_result.get("state", {}).get("scans") or []),
    }
    if push_error:
        out["push_error"] = push_error
    return out


def render_intraday_scan_markdown(
    scan: dict[str, Any],
    lookback_mss: float,
    lookback_detail: list[dict[str, Any]],
    trend: str,
    report: dict[str, Any],
    *,
    scan_count: Optional[int] = None,
) -> str:
    trend_map = {
        "rising": "上升",
        "falling": "下降",
        "turning_up": "拐点向上",
        "turning_down": "拐点向下",
        "flat": "横盘",
        "mixed": "震荡",
        "insufficient": "数据不足",
    }
    lines = [
        f"**{scan['scan_id']} 数据收集完成**",
        "",
        f"**即时 MSS：** {scan.get('mss_final')} 分 · **标签：** {scan.get('verdict')}",
        f"**Lookback MSS：** {lookback_mss} 分 · **趋势：** {trend_map.get(trend, trend)}",
    ]
    total = scan_count if scan_count is not None else len(lookback_detail)
    if total > 1:
        lines.append(f"**今日累计扫描：** {total} 次")
    if lookback_detail:
        lines.extend(["", "**Lookback 加权拆解：**"])
        for item in lookback_detail:
            lines.append(
                f"- {item['scan_id']}: MSS {item['mss_final']} × {item['weight']:.0%} "
                f"= {item['weighted']}"
            )
    if report.get("reasoning"):
        lines.extend(["", f"**研判：** {report['reasoning']}"])
    return "\n".join(lines)


def render_intraday_trade_markdown(
    decision: TradeDecision,
    lookback_detail: list[dict[str, Any]],
    report: dict[str, Any],
    scans: list[dict[str, Any]],
) -> str:
    action_map = {"buy": "买入", "sell": "卖出", "hold": "观望", "skip": "跳过"}
    lines = [
        f"**{decision.trade_id or '调仓评估'} · {action_map.get(decision.action, decision.action)}**",
        "",
        f"**Lookback MSS：** {decision.lookback_mss} 分 · **趋势：** {decision.trend}",
        f"**决策：** {decision.reasoning}",
    ]
    if decision.friction_blocked:
        lines.append("⚠️ **摩擦惩罚阻断：** 预期收益不足以覆盖佣金与滑点")
    if decision.blocked:
        lines.append("⚠️ **风控阻断：** 当前不允许执行买入")

    lines.extend(["", "**前序扫描回顾：**"])
    for s in scans[-3:]:
        lines.append(f"- {s['scan_id']}: MSS {s.get('mss_final')} · {s.get('verdict')}")

    if lookback_detail:
        lines.extend(["", "**Lookback 权重计算：**"])
        for item in lookback_detail:
            lines.append(
                f"- {item['scan_id']}: {item['mss_final']} × {item['weight']:.0%} = {item['weighted']}"
            )

    if report.get("invalidation"):
        lines.extend(["", f"**失效条件：** {report['invalidation']}"])
    return "\n".join(lines)


def _harness_overlay_note(settings: dict[str, Any]) -> str:
    overlay = (settings.get("harness_runtime") or {}).get("threshold_overlay") or {}
    if not overlay:
        return ""
    parts = []
    for key, row in overlay.items():
        if key == "min_cash_ratio":
            parts.append(f"{key} {row['base']:.0%}→{row['effective']:.0%}")
        elif key == "max_price_deviation_pct":
            parts.append(f"{key} {row['base']:.1%}→{row['effective']:.1%}")
        else:
            parts.append(f"{key} {row['base']:.0f}→{row['effective']:.0f}")
    return f"（harness: {', '.join(parts)}）"


def _decide_trade(
    *,
    lookback_mss: float,
    trend: str,
    verdict: Any,
    report: dict[str, Any],
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    trade_index: int,
    expected_return_pct: Optional[float],
) -> TradeDecision:
    trading = settings.get("trading", {})
    macro_veto = macro_veto_default(settings)
    aggressive = aggressive_entry_default(settings)
    min_cash = min_cash_ratio_default(settings)

    trade_id = f"T{trade_index}"
    portfolio = snapshot.get("portfolio") or {}
    cash_ratio = portfolio.get("cash_ratio")
    overlay_note = _harness_overlay_note(settings)

    exp_ret = expected_return_pct
    if exp_ret is None:
        exp_ret = _estimate_expected_return(lookback_mss, aggressive, macro_veto)

    friction_blocked = not _passes_friction(exp_ret, settings)
    blocked = verdict.blocked or report.get("blocked", False)

    if lookback_mss < macro_veto:
        return TradeDecision(
            action="sell" if _has_sellable_holdings(snapshot, settings) else "hold",
            trade_id=trade_id,
            lookback_mss=lookback_mss,
            lookback_detail=[],
            trend=trend,
            reasoning=f"Lookback MSS {lookback_mss:.0f} 低于否决线 {macro_veto:.0f}，宏观避险{overlay_note}",
            blocked=False,
            friction_blocked=False,
            expected_return_pct=exp_ret,
        )

    if blocked:
        return TradeDecision(
            action="hold",
            trade_id=trade_id,
            lookback_mss=lookback_mss,
            lookback_detail=[],
            trend=trend,
            reasoning=f"标签 {verdict.verdict} 阻断买入（即时 MSS {verdict.mss_final:.0f}）",
            blocked=True,
            friction_blocked=friction_blocked,
            expected_return_pct=exp_ret,
        )

    if lookback_mss >= aggressive and trend in ("rising", "turning_up"):
        buy_block = None
        from agent_reach.daily_run.skill_rejected import trade_blocked_by_rejected

        buy_block = trade_blocked_by_rejected(
            "buy",
            code=str(report.get("code") or ""),
            name=str(report.get("name") or ""),
            settings=settings,
        )
        if buy_block:
            return TradeDecision(
                action="hold",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"已证伪策略阻断买入：{buy_block}{overlay_note}",
                blocked=True,
                friction_blocked=friction_blocked,
                expected_return_pct=exp_ret,
            )
        if cash_ratio is not None and cash_ratio < min_cash:
            return TradeDecision(
                action="hold",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"现金比例 {cash_ratio:.0%} 低于最低 {min_cash:.0%}，暂不加仓{overlay_note}",
                blocked=True,
                friction_blocked=friction_blocked,
                expected_return_pct=exp_ret,
            )
        if friction_blocked:
            return TradeDecision(
                action="hold",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"MSS 达 {lookback_mss:.0f} 但预期收益 {exp_ret:.2%} 不足以覆盖摩擦成本",
                blocked=False,
                friction_blocked=True,
                expected_return_pct=exp_ret,
            )
        return TradeDecision(
            action="buy",
            trade_id=trade_id,
            lookback_mss=lookback_mss,
            lookback_detail=[],
            trend=trend,
            reasoning=f"Lookback MSS {lookback_mss:.0f} ≥ {aggressive:.0f} 且趋势 {trend}，条件性建仓{overlay_note}",
            blocked=False,
            friction_blocked=False,
            expected_return_pct=exp_ret,
        )

    runtime = settings.get("harness_runtime") or {}
    trade_signals = runtime.get("trade_signals") or {}
    if (
        trade_signals.get("defensive_trim")
        and trend in ("falling", "turning_down")
        and lookback_mss >= macro_veto
        and _has_sellable_holdings(snapshot, settings)
    ):
        return TradeDecision(
            action="sell",
            trade_id=trade_id,
            lookback_mss=lookback_mss,
            lookback_detail=[],
            trend=trend,
            reasoning=(
                f"Harness MSS预测偏离/偏差信号 + 趋势 {trend}，"
                f"Lookback MSS {lookback_mss:.0f} ≥ 否决线 {macro_veto:.0f}，防御性减仓{overlay_note}"
            ),
            blocked=False,
            friction_blocked=False,
            expected_return_pct=exp_ret,
        )

    return TradeDecision(
        action="hold",
        trade_id=trade_id,
        lookback_mss=lookback_mss,
        lookback_detail=[],
        trend=trend,
        reasoning=f"Lookback MSS {lookback_mss:.0f}，趋势 {trend}，维持观望{overlay_note}",
        blocked=False,
        friction_blocked=friction_blocked,
        expected_return_pct=exp_ret,
    )


def _passes_friction(expected_return_pct: float, settings: dict[str, Any]) -> bool:
    return expected_return_pct > friction_min_return_default(settings)


def _estimate_expected_return(mss: float, aggressive: float, macro_veto: float) -> float:
    if mss >= aggressive:
        return 0.015 + (mss - aggressive) * 0.001
    if mss <= macro_veto:
        return -0.02
    return 0.005


def _holding_locked(snapshot: dict[str, Any], settings: dict[str, Any]) -> bool:
    from agent_reach.daily_run.portfolio_manager import holding_is_sellable

    holdings = (snapshot.get("portfolio") or {}).get("holdings") or []
    if not holdings:
        return False
    return not any(holding_is_sellable(h, settings) for h in holdings)


def _has_sellable_holdings(snapshot: dict[str, Any], settings: dict[str, Any]) -> bool:
    from agent_reach.daily_run.portfolio_manager import holding_is_sellable

    return any(
        holding_is_sellable(h, settings)
        for h in (snapshot.get("portfolio") or {}).get("holdings") or []
    )


def _today_str() -> str:
    return today_shanghai().isoformat()

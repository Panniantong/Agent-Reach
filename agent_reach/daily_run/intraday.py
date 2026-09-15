# -*- coding: utf-8 -*-
"""Intraday scan (S1-S12) and trade (T1-T5) workflow with lookback MSS."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.lookback import compute_lookback_mss, detect_mss_trend
from agent_reach.daily_run.defensive_trim_guards import evaluate_defensive_trim_sell
from agent_reach.daily_run.intraday_policy import (
    effective_aggressive_entry,
    estimate_expected_return,
    intraday_audit_block_reason,
    kronos_buy_block_reason,
    trend_allows_buy,
    trend_triggers_eval,
)
from agent_reach.daily_run.pipeline import evaluate_snapshot, render_markdown
from agent_reach.daily_run.harness_policy import (
    aggressive_entry_default,
    macro_veto_default,
    min_cash_ratio_default,
    runtime_int_default,
)
from agent_reach.daily_run.pnl_execution_guard import (
    pnl_buy_block_reason,
    pnl_symbol_ledger_block_reason,
)
from agent_reach.daily_run.settings import effective_settings, load_settings
from agent_reach.daily_run.trade_calendar import is_continuous_session, today_shanghai


from agent_reach.daily_run.schedule import INTRADAY_MAX_SCANS as MAX_SCANS

MAX_TRADES = 5  # legacy alias; prefer max_applied_trades_per_day / max_trade_evaluations_per_symbol


def max_applied_trades_per_day(settings: Optional[dict[str, Any]] = None) -> int:
    cfg = effective_settings(settings or load_settings())
    return max(1, runtime_int_default(cfg, "schedule", "max_applied_trades_per_day"))


def max_trade_evaluations_per_symbol(settings: Optional[dict[str, Any]] = None) -> int:
    cfg = effective_settings(settings or load_settings())
    return max(1, runtime_int_default(cfg, "schedule", "max_trade_evaluations_per_symbol"))


def count_trade_evaluations(trades: list[dict[str, Any]] | None) -> int:
    """Buy/sell evaluations toward per-symbol cap; hold/skip do not count."""
    return sum(
        1
        for t in trades or []
        if str(t.get("action") or "").strip().lower() not in ("", "hold", "skip")
    )


def consecutive_buy_recommendations(
    trades: list[dict[str, Any]] | None,
    code: str,
) -> int:
    """Trailing count of consecutive buy recommendations for one symbol."""
    from agent_reach.daily_run.snapshot_builder import _normalize_code

    norm = _normalize_code(code)
    streak = 0
    for rec in reversed(list(trades or [])):
        rec_code = _normalize_code(str(rec.get("code") or ""))
        if rec_code and rec_code != norm:
            break
        if str(rec.get("action") or "").strip().lower() == "buy":
            streak += 1
        else:
            break
    return streak


def consecutive_buy_cash_bypass_threshold(settings: Optional[dict[str, Any]] = None) -> int:
    cfg = effective_settings(settings)
    intraday = cfg.get("intraday") or {}
    if intraday.get("consecutive_buy_cash_bypass_enabled") is False:
        return 0
    from agent_reach.daily_run.harness_policy import intraday_buy_policy_default

    return intraday_buy_policy_default(cfg, "consecutive_buy_cash_bypass")


def deep_loss_consecutive_buy_threshold(settings: Optional[dict[str, Any]] = None) -> int:
    cfg = effective_settings(settings)
    intraday = cfg.get("intraday") or {}
    if intraday.get("deep_loss_consecutive_buy_enabled") is False:
        return 0
    from agent_reach.daily_run.harness_policy import intraday_buy_policy_default

    return intraday_buy_policy_default(cfg, "deep_loss_consecutive_buy")


def deep_loss_buy_block_reason(
    trades: list[dict[str, Any]] | None,
    code: str,
    snapshot: dict[str, Any],
    *,
    current_action: str,
    settings: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Block add-position buys on deep-loss holdings until N consecutive buy signals."""
    threshold = deep_loss_consecutive_buy_threshold(settings)
    if threshold <= 0 or str(current_action or "").strip().lower() != "buy":
        return None
    from agent_reach.daily_run.portfolio_manager import symbol_is_deep_loss_holding
    from agent_reach.daily_run.snapshot_builder import _normalize_code

    symbol_code = _normalize_code(str(code or ""))
    if not symbol_code or not symbol_is_deep_loss_holding(snapshot, effective_settings(settings), symbol_code):
        return None
    streak = consecutive_buy_recommendations(trades, symbol_code) + 1
    if streak >= threshold:
        return None
    name = str(snapshot.get("name") or symbol_code).strip()
    for holding in (snapshot.get("portfolio") or {}).get("holdings") or []:
        if _normalize_code(str(holding.get("code") or "")) == symbol_code:
            name = str(holding.get("name") or name)
            break
    return (
        f"{name} 深度套牢，需连续 {threshold} 次买入建议才允许加仓"
        f"（当前 {streak}/{threshold}）"
    )


def should_apply_consecutive_buy_cash_bypass(
    trades: list[dict[str, Any]] | None,
    code: str,
    *,
    current_action: str,
    settings: Optional[dict[str, Any]] = None,
) -> bool:
    threshold = consecutive_buy_cash_bypass_threshold(settings)
    if threshold <= 0 or str(current_action or "").strip().lower() != "buy":
        return False
    streak = consecutive_buy_recommendations(trades, code) + 1
    return streak >= threshold


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

    if sched.get("intraday_session_gate_enabled", True) and not is_continuous_session():
        return "当前非连续竞价时段（09:30-11:30 / 13:00-14:57），仅记录扫描不评估调仓"

    st = state or load_state(state_path)
    min_scans = runtime_int_default(cfg, "schedule", "trade_min_scans")
    if len(st.scans) < min_scans:
        return f"扫描次数不足（需 ≥{min_scans} 次，当前 {len(st.scans)} 次）"

    eval_cap = max_trade_evaluations_per_symbol(cfg)
    if count_trade_evaluations(st.trades) >= eval_cap:
        return f"本标的调仓评估已达上限（buy/sell 已 {eval_cap} 次，hold 不计入）"

    trend = detect_mss_trend(st.scans, cfg)
    every_n = runtime_int_default(cfg, "schedule", "trade_every_n_scans")
    if trend_triggers_eval(cfg, trend):
        return "内部状态异常：趋势已变化但未触发评估"

    return (
        f"未命中调仓评估节奏（趋势 {trend}，每 {every_n} 次扫描评估一次；"
        f"当前 S{len(st.scans)}）"
    )


TRADE_BLOCK_MESSAGES: dict[str, str] = {
    "audit": "⚠️ **风控阻断：** 数据审计未通过，暂停交易",
    "buy_verdict": "⚠️ **风控阻断：** 当前标签不允许买入",
    "buy_rejected": "⚠️ **风控阻断：** 已证伪策略不允许买入",
    "buy_pnl": "⚠️ **风控阻断：** 盈亏纪律不允许新开仓",
    "buy_ledger": "⚠️ **风控阻断：** 标的账本不允许买入",
    "buy_kronos": "⚠️ **风控阻断：** Kronos 看空信号，不允许买入",
    "buy_cash": "⚠️ **风控阻断：** 现金比例不足，不允许加仓",
    "buy_budget": "⚠️ **风控阻断：** 可部署买入预算不足一手，维持观望",
    "buy_deep_loss": "⚠️ **风控阻断：** 深度套牢标的需连续 3 次买入建议才允许加仓",
    "sell_deep_loss": "⚠️ **风控阻断：** 深度套牢且组合覆盖不足，暂不允许卖出",
    "sell_defensive_trim": (
        "⚠️ **风控阻断：** Lookback 已进入回暖区，记忆驱动防御减仓暂缓，维持观望"
    ),
    "sell_week_open_hold_debounce": (
        "⚠️ **风控阻断：** 周日计划为「持有」，defensive_trim 需连续确认后再减仓"
    ),
    "sell_profit_lock": "⚠️ **风控阻断：** 动态止盈条件未满足或今日已执行，维持观望",
}


@dataclass
class TradeDecision:
    action: str  # buy | sell | hold | skip
    trade_id: Optional[str]
    lookback_mss: float
    lookback_detail: list[dict[str, Any]]
    trend: str
    reasoning: str
    blocked: bool = False
    block_kind: Optional[str] = None
    friction_blocked: bool = False
    expected_return_pct: Optional[float] = None
    evaluation: Optional[dict[str, Any]] = None
    sell_kind: Optional[str] = None
    sell_ratio_override: Optional[float] = None
    max_position_pct_override: Optional[float] = None
    watchlist_breakout: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = {
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
        if self.block_kind:
            payload["block_kind"] = self.block_kind
        if self.sell_kind:
            payload["sell_kind"] = self.sell_kind
        if self.sell_ratio_override is not None:
            payload["sell_ratio_override"] = self.sell_ratio_override
        if self.max_position_pct_override is not None:
            payload["max_position_pct_override"] = self.max_position_pct_override
        if self.watchlist_breakout:
            payload["watchlist_breakout"] = True
        return payload


@dataclass
class IntradayState:
    date: str
    scans: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    hold_debounce_strikes: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "date": self.date,
            "scans": self.scans,
            "trades": self.trades,
        }
        if self.hold_debounce_strikes:
            payload["hold_debounce_strikes"] = dict(self.hold_debounce_strikes)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntradayState:
        raw_strikes = data.get("hold_debounce_strikes") or {}
        strikes = {
            str(k): int(v)
            for k, v in raw_strikes.items()
            if str(k).strip() and v is not None
        }
        return cls(
            date=str(data.get("date", _today_str())),
            scans=list(data.get("scans") or []),
            trades=list(data.get("trades") or []),
            hold_debounce_strikes=strikes,
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


def scan_id_number(scan_id: Optional[str]) -> int:
    """Parse S_n → n; unknown labels → 0."""
    if not scan_id:
        return 0
    label = str(scan_id).strip().upper()
    if label.startswith("S") and label[1:].isdigit():
        return int(label[1:])
    return 0


def pick_batch_scan_id(scan_ids: list[Optional[str]]) -> Optional[str]:
    """Merged intraday cards should use the highest S_n produced in the batch."""
    nums = [scan_id_number(s) for s in scan_ids if s]
    if not nums:
        return None
    return f"S{max(nums)}"


def next_scan_id_for_codes(codes: Optional[list[str]] = None) -> tuple[Optional[str], bool]:
    """Next batch scan label from per-symbol states (max eligible count + 1)."""
    if not codes:
        count = len(load_state().scans)
        at_limit = count >= MAX_SCANS
        return (None if at_limit else f"S{count + 1}", at_limit)

    counts: list[int] = []
    for code in codes:
        if code in (None, "MARKET"):
            counts.append(len(load_state().scans))
        else:
            counts.append(len(load_state(code=code).scans))

    eligible = [c for c in counts if c < MAX_SCANS]
    if not eligible:
        return None, True
    return f"S{max(eligible) + 1}", False


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
    try:
        from agent_reach.daily_run.storage.hooks import on_intraday_state

        sym = p.stem if p.parent.name == "intraday" else ""
        on_intraday_state(state.to_dict(), code=sym, source_path=str(p))
    except Exception:
        pass
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

    from agent_reach.daily_run.team import enrich_with_team_or_experts

    enriched, _expert_steps = enrich_with_team_or_experts(
        dict(snapshot),
        cfg,
        workflow="intraday",
        plugin_names=plugin_names,
    )
    enriched.setdefault("report_type", "intraday")
    enriched.setdefault("as_of", datetime.now(timezone.utc).isoformat())

    evaluation = evaluate_snapshot(enriched, cfg, doctor_channels=doctor_channels)
    from agent_reach.daily_run.session_verdict_guards import apply_session_pullback_verdict_downgrade

    apply_session_pullback_verdict_downgrade(
        evaluation,
        enriched,
        st.scans,
        cfg,
        pending_scan_num=len(st.scans) + 1,
    )
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
    try:
        from agent_reach.daily_run.storage.hooks import on_intraday_scan

        sym = str(entry.get("code") or "")
        sp = str(state_path or default_state_path(sym or None))
        on_intraday_scan(entry, code=sym, source_path=sp)
    except Exception:
        pass

    lookback_mss, lookback_detail = compute_lookback_mss(st.scans, cfg)
    trend = detect_mss_trend(st.scans, cfg)

    from agent_reach.daily_run.macro_collector import fetch_intraday_xueqiu_cross_alerts

    pf = enriched.get("portfolio") or {}
    xueqiu_cross = fetch_intraday_xueqiu_cross_alerts(pf, settings=cfg)

    markdown = render_intraday_scan_markdown(
        entry,
        lookback_mss,
        lookback_detail,
        trend,
        report,
        scan_count=len(st.scans),
        settings=cfg,
        macro_signals=xueqiu_cross,
        enriched=enriched,
    )

    return {
        "scan": entry,
        "enriched": enriched,
        "state": st.to_dict(),
        "evaluation": evaluation,
        "lookback_mss": lookback_mss,
        "lookback_detail": lookback_detail,
        "trend": trend,
        "xueqiu_cross": xueqiu_cross,
        "markdown": markdown,
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
    cfg = effective_settings(settings)
    sym = code or enriched.get("code")
    resolved_path = state_path or (default_state_path(sym) if sym else default_state_path())
    st = state or load_state(resolved_path, code=sym)

    if len(st.scans) >= MAX_SCANS:
        raise RuntimeError(f"今日扫描已达上限 {MAX_SCANS} 次（S1-S{MAX_SCANS}）")

    from agent_reach.daily_run.session_verdict_guards import apply_session_pullback_verdict_downgrade

    apply_session_pullback_verdict_downgrade(
        evaluation,
        enriched,
        st.scans,
        cfg,
        pending_scan_num=len(st.scans) + 1,
    )
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
    if source == "midday":
        from agent_reach.daily_run.midday import midday_cfg
        from agent_reach.daily_run.trade_calendar import is_lunch_break

        mcfg = midday_cfg(cfg)
        if mcfg.get("exclude_from_trend", True) or is_lunch_break():
            entry["trend_excluded"] = True
            entry["quote_stale"] = True
            entry["lookback_weight_scale"] = float(mcfg.get("lookback_weight_scale", 0.25))
    st.scans.append(entry)
    save_state(st, resolved_path)

    lookback_mss, lookback_detail = compute_lookback_mss(st.scans, cfg)
    trend = detect_mss_trend(st.scans, cfg)
    from agent_reach.daily_run.intraday_scan_filters import scans_for_trend_detection

    anchor_trend = detect_mss_trend(scans_for_trend_detection(st.scans), cfg)

    from agent_reach.daily_run.macro_collector import fetch_intraday_xueqiu_cross_alerts

    pf = enriched.get("portfolio") or {}
    xueqiu_cross = fetch_intraday_xueqiu_cross_alerts(pf, settings=cfg)

    markdown = render_intraday_scan_markdown(
        entry,
        lookback_mss,
        lookback_detail,
        trend,
        report,
        scan_count=len(st.scans),
        settings=cfg,
        macro_signals=xueqiu_cross,
        enriched=enriched,
    )

    return {
        "scan": entry,
        "state": st.to_dict(),
        "lookback_mss": lookback_mss,
        "lookback_detail": lookback_detail,
        "trend": trend,
        "anchor_trend": anchor_trend,
        "xueqiu_cross": xueqiu_cross,
        "markdown": markdown,
    }


def should_evaluate_trade(
    state: Optional[IntradayState] = None,
    settings: Optional[dict[str, Any]] = None,
    *,
    state_path: Optional[Path] = None,
) -> bool:
    """Heuristic: trade after ≥ trade_min_scans scans, on trend shift or every N scans."""
    from agent_reach.daily_run.intraday_rebound import intraday_rebound_active
    from agent_reach.daily_run.pm_session_overlay import apply_intraday_session_overlays

    st = state or load_state(state_path)
    if settings is not None and intraday_rebound_active(settings):
        cfg = settings
    else:
        cfg = effective_settings(settings)
        cfg = apply_intraday_session_overlays(cfg, st.scans)
    sched = cfg.get("schedule", {})
    if not sched.get("intraday_trade_enabled", True):
        return False

    # Pre-open (S1-S2 ~07:00-09:00) and post-close (S12 ~15:00) scans record
    # data but must not fire buy/sell — no continuous-matching session exists
    # to fill them. Lunch break (11:30-13:00) is likewise excluded.
    if sched.get("intraday_session_gate_enabled", True) and not is_continuous_session():
        return False

    if len(st.scans) < runtime_int_default(cfg, "schedule", "trade_min_scans"):
        return False
    if count_trade_evaluations(st.trades) >= max_trade_evaluations_per_symbol(cfg):
        return False

    trend = detect_mss_trend(st.scans, cfg)
    if trend_triggers_eval(cfg, trend):
        return True
    every_n = runtime_int_default(cfg, "schedule", "trade_every_n_scans")
    return len(st.scans) % every_n == 0


def apply_paper_trade(
    decision: TradeDecision,
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    cash_limit_bypass: bool = False,
) -> "ApplyResult":
    """Apply paper buy/sell to portfolio.json when auto_adjust is enabled."""
    from agent_reach.daily_run.portfolio_manager import (
        ApplyResult,
        append_trade_ledger,
        applied_trades_today_for,
        apply_auto_adjust,
        is_auto_adjust_enabled,
        register_applied_trade,
    )
    from agent_reach.daily_run.snapshot_builder import _PORTFOLIO_IO_LOCK, load_portfolio, save_portfolio
    from agent_reach.daily_run.symbols import sync_snapshot_portfolio

    cfg = effective_settings(settings)
    _merge_keys = ("price", "change_pct", "name", "ma20", "volume", "turnover")

    with _PORTFOLIO_IO_LOCK:
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
                row.update({k: quote_map[code][k] for k in _merge_keys if quote_map[code].get(k) is not None})
        merged_watchlist = []
        for row in snap.get("watchlist") or []:
            item = dict(row)
            code = _normalize_code(str(item.get("code", "")))
            if code in quote_map:
                item.update({k: quote_map[code][k] for k in _merge_keys if quote_map[code].get(k) is not None})
            merged_watchlist.append(item)
        snap["watchlist"] = merged_watchlist

        action = decision.action
        applied_cap = max_applied_trades_per_day(cfg)
        cap_code = _normalize_code(str(snapshot.get("code") or ""))
        if action in ("buy", "sell") and applied_trades_today_for(cap_code, cfg) >= applied_cap:
            scope = str((cfg.get("schedule") or {}).get("max_applied_trades_per_day_scope") or "global")
            scope_label = "本标的" if scope == "per_symbol" else "全组合"
            return ApplyResult(
                applied=False,
                portfolio=pf,
                message=(
                    f"今日{scope_label}落账已达上限 {applied_cap} 次，"
                    f"{'买入' if action == 'buy' else '卖出'}信号仅记录不落账"
                ),
            )

        result = apply_auto_adjust(
            pf,
            decision,
            snap,
            cfg,
            allow_watchlist_changes=False,
            cash_limit_bypass=cash_limit_bypass,
        )
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
            enriched = append_trade_ledger(
                result.actions,
                trade_id=decision.trade_id,
                decision_action=decision.action,
            )
            result.action_payloads = enriched
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
    from agent_reach.daily_run.pm_session_overlay import apply_intraday_session_overlays

    cfg = apply_intraday_session_overlays(cfg, st.scans)

    try:
        from agent_reach.daily_run.defensive_trim_guards import maybe_persist_intraday_macro_warming

        maybe_persist_intraday_macro_warming(settings=cfg)
    except Exception:
        pass

    eval_cap = max_trade_evaluations_per_symbol(cfg)
    if count_trade_evaluations(st.trades) >= eval_cap:
        raise RuntimeError(
            f"今日调仓评估已达上限 {eval_cap} 次（buy/sell，hold 不计入）"
        )
    if not st.scans:
        raise RuntimeError("尚无扫描记录，请先运行 daily-run intraday scan")

    if pre_enriched is not None and pre_evaluation is not None:
        enriched = pre_enriched
        evaluation = pre_evaluation
    else:
        from agent_reach.daily_run.team import enrich_with_team_or_experts

        enriched, _expert_steps = enrich_with_team_or_experts(
            dict(snapshot),
            cfg,
            workflow="intraday",
            plugin_names=plugin_names,
        )
        enriched.setdefault("report_type", "intraday")
        evaluation = evaluate_snapshot(enriched, cfg, doctor_channels=doctor_channels)

    report = evaluation["report"]
    verdict = evaluation["verdict"]

    lookback_mss, lookback_detail = compute_lookback_mss(st.scans, cfg)
    trend = detect_mss_trend(st.scans, cfg)
    decision = _decide_trade(
        lookback_mss=lookback_mss,
        trend=trend,
        verdict=verdict,
        report=report,
        snapshot=enriched,
        settings=cfg,
        trade_index=len(st.trades) + 1,
        expected_return_pct=expected_return_pct,
        prior_trades=st.trades,
        session_scans=st.scans,
        hold_debounce_strikes=st.hold_debounce_strikes,
    )

    symbol_code = str(report.get("code") or "")
    cash_limit_bypass = should_apply_consecutive_buy_cash_bypass(
        st.trades,
        symbol_code,
        current_action=decision.action,
        settings=cfg,
    )
    consecutive_buy_streak = consecutive_buy_recommendations(st.trades, symbol_code) + (
        1 if decision.action == "buy" else 0
    )

    from agent_reach.daily_run.portfolio_manager import ApplyResult, trade_buy_budget_blocked

    trade_record = {
        **decision.to_dict(),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "verdict": report.get("verdict"),
        "mss_final": report.get("mss_final"),
        "code": report.get("code"),
        "name": report.get("name"),
        "consecutive_buy_streak": consecutive_buy_streak if decision.action == "buy" else None,
        "cash_limit_bypass": cash_limit_bypass or None,
    }
    if trade_buy_budget_blocked(decision.to_dict()) and decision.blocked:
        pf = enriched.get("portfolio") or {}
        apply_result = ApplyResult(
            applied=False,
            portfolio=pf,
            message=str(decision.reasoning or "决策层预算预检阻断"),
        )
    else:
        apply_result = apply_paper_trade(
            decision,
            enriched,
            settings=cfg,
            cash_limit_bypass=cash_limit_bypass,
        )
    trade_record["portfolio_applied"] = apply_result.applied
    trade_record["portfolio_message"] = apply_result.message
    try:
        from agent_reach.daily_run.execution_quality import enrich_trade_execution_quality
        from agent_reach.daily_run.nested_decision import attach_nested_decision_to_trade

        enrich_trade_execution_quality(trade_record, apply_result=apply_result, settings=cfg)
        attach_nested_decision_to_trade(trade_record, decision, settings=cfg)
    except Exception:
        pass
    if apply_result.applied:
        payloads = apply_result.action_payloads or [
            a.to_dict() for a in (apply_result.actions or [])
        ]
        trade_record["portfolio_actions"] = payloads
    try:
        from agent_reach.daily_run.context_store import record_trade_case

        pf = enriched.get("portfolio") or {}
        case_uri = record_trade_case(
            trade_record,
            portfolio_snapshot={
                "cash": pf.get("cash"),
                "total": pf.get("total"),
                "cash_ratio": pf.get("cash_ratio"),
            },
            price=enriched.get("price"),
            settings=cfg,
        )
        if case_uri:
            trade_record["case_uri"] = case_uri
    except Exception:
        pass
    st.trades.append(trade_record)
    save_state(st, state_path)

    from agent_reach.daily_run.portfolio_manager import render_apply_markdown

    markdown = render_intraday_trade_markdown(
        decision,
        lookback_detail,
        report,
        st.scans,
        settings=cfg,
        enriched=enriched,
    )
    markdown = markdown + "\n\n---\n\n" + render_apply_markdown(apply_result, decision=decision)

    return {
        "decision": decision.to_dict(),
        "trade": trade_record,
        "state": st.to_dict(),
        "evaluation": evaluation,
        "portfolio_apply": apply_result.to_dict(),
        "markdown": markdown,
    }


def build_intraday_trade_audit_summary(
    enriched: dict[str, Any],
    evaluation: dict[str, Any],
    state: IntradayState,
    *,
    settings: Optional[dict[str, Any]] = None,
    skip_reason: Optional[str] = None,
    expected_return_pct: Optional[float] = None,
) -> dict[str, Any]:
    """Dry-run trade decision for every scan; does not persist T_n or apply portfolio."""
    cfg = effective_settings(settings)
    from agent_reach.daily_run.pm_session_overlay import apply_intraday_session_overlays

    cfg = apply_intraday_session_overlays(cfg, state.scans)
    report = evaluation["report"]
    verdict = evaluation["verdict"]
    lookback_mss, lookback_detail = compute_lookback_mss(state.scans, cfg)
    trend = detect_mss_trend(state.scans, cfg)
    decision = _decide_trade(
        lookback_mss=lookback_mss,
        trend=trend,
        verdict=verdict,
        report=report,
        snapshot=enriched,
        settings=cfg,
        trade_index=len(state.trades) + 1,
        expected_return_pct=expected_return_pct,
        prior_trades=state.trades,
        session_scans=state.scans,
        hold_debounce_strikes=state.hold_debounce_strikes,
    )
    markdown = render_intraday_trade_markdown(
        decision,
        lookback_detail,
        report,
        state.scans,
        settings=cfg,
        enriched=enriched,
        audit_only=True,
        skip_reason=skip_reason,
    )
    return {
        "decision": decision.to_dict(),
        "markdown": markdown,
        "audit_only": True,
        "skip_reason": skip_reason,
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

    enriched = scan_result.get("enriched") or snapshot
    try:
        from agent_reach.daily_run.technical_scenario_watch import (
            evaluate_active_scenarios,
            format_technical_scenario_markdown,
        )

        scenario_evals = evaluate_active_scenarios(enriched, settings=cfg)
        scenario_md = format_technical_scenario_markdown(scenario_evals)
        if scenario_md:
            scan_result["markdown"] = (scan_result.get("markdown") or "") + "\n\n---\n\n" + scenario_md
            scan_result["technical_scenarios"] = scenario_evals
    except Exception:
        pass

    st_after_scan = IntradayState.from_dict(scan_result["state"])
    from agent_reach.daily_run.pm_session_overlay import apply_intraday_session_overlays

    cfg = apply_intraday_session_overlays(cfg, st_after_scan.scans)
    do_trade = trade or should_evaluate_trade(st_after_scan, cfg, state_path=state_path)
    skip_reason: Optional[str] = None
    if not do_trade:
        skip_reason = explain_trade_skip_reason(st_after_scan, cfg, state_path=state_path)
        scan_result["trade_skip_reason"] = skip_reason

    trade_result: Optional[dict[str, Any]] = None
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
    else:
        evaluation = scan_result.get("evaluation")
        if evaluation:
            trade_result = build_intraday_trade_audit_summary(
                scan_result.get("enriched") or snapshot,
                evaluation,
                st_after_scan,
                settings=cfg,
                skip_reason=skip_reason,
                expected_return_pct=expected_return_pct,
            )
            steps.append("audit_summary")

    feishu_result = None
    narrative_feishu = None
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
            from agent_reach.daily_run.report_narrative import push_intraday_narrative_card

            narrative_feishu = push_intraday_narrative_card(
                cfg_obj,
                cfg,
                scan_id=scan_id,
                symbol_count=1,
                scan_result=scan_result,
                trade_result=trade_result,
            )
            if narrative_feishu:
                steps.append("narrative_push")
        except FeishuError as exc:
            push_error = str(exc)

    out: dict[str, Any] = {
        "steps": steps,
        "scan": scan_result,
        "trade": trade_result,
        "feishu": feishu_result,
        "narrative_feishu": narrative_feishu if push else None,
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
    settings: Optional[dict[str, Any]] = None,
    macro_signals: Optional[dict[str, Any]] = None,
    enriched: Optional[dict[str, Any]] = None,
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
    from agent_reach.daily_run.session_verdict_guards import (
        render_session_pullback_markdown,
        render_watchlist_drawdown_markdown,
    )

    pullback_md = render_session_pullback_markdown(report)
    if pullback_md:
        lines.extend(["", pullback_md])
    pf = (enriched or {}).get("portfolio") or {}
    watchlist_md = render_watchlist_drawdown_markdown(pf, settings=settings)
    if watchlist_md:
        lines.extend(["", watchlist_md])
    from agent_reach.daily_run.xueqiu_hot_display import render_intraday_xueqiu_alert_markdown

    alert_md = render_intraday_xueqiu_alert_markdown(macro_signals)
    if alert_md:
        lines.extend(["", alert_md])
    if enriched and (enriched.get("team_review") or enriched.get("expert_results")):
        from agent_reach.daily_run.team import expert_card_enabled, render_team_markdown

        if settings is None or expert_card_enabled(settings, workflow="intraday"):
            team_md = render_team_markdown(enriched)
            if team_md:
                lines.extend(["", team_md])
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
    if settings is not None:
        from agent_reach.daily_run.harness_display import (
            format_lookback_overlay_markdown,
            format_mss_weights_overlay_markdown,
        )

        lookback_md = format_lookback_overlay_markdown(settings)
        if lookback_md:
            lines.extend(["", lookback_md])
        mss_weights_md = format_mss_weights_overlay_markdown(settings)
        if mss_weights_md:
            lines.extend(["", mss_weights_md])
    if report.get("reasoning"):
        lines.extend(["", f"**研判：** {report['reasoning']}"])
    return "\n".join(lines)


def infer_trade_block_kind(decision: TradeDecision | dict[str, Any]) -> Optional[str]:
    if isinstance(decision, dict):
        blocked = decision.get("blocked", False)
        block_kind = decision.get("block_kind")
        reasoning = str(decision.get("reasoning") or "")
    else:
        blocked = decision.blocked
        block_kind = decision.block_kind
        reasoning = decision.reasoning or ""

    if not blocked:
        return None
    if block_kind:
        return str(block_kind)
    if "深度套牢" in reasoning or "暂不卖" in reasoning:
        return "sell_deep_loss"
    if "已证伪策略" in reasoning:
        return "buy_rejected"
    if "Kronos" in reasoning:
        return "buy_kronos"
    if "现金比例" in reasoning:
        return "buy_cash"
    if "可部署买入预算" in reasoning or "不足一手" in reasoning:
        return "buy_budget"
    if "审计" in reasoning:
        return "audit"
    if "阻断买入" in reasoning or ("标签" in reasoning and "阻断" in reasoning):
        return "buy_verdict"
    if "账本" in reasoning or "ledger" in reasoning.lower():
        return "buy_ledger"
    if "连亏" in reasoning or "胜率" in reasoning:
        return "buy_pnl"
    if "深度套牢" in reasoning and "加仓" in reasoning:
        return "buy_deep_loss"
    return "buy_verdict"


def format_buy_budget_block_message(decision: TradeDecision | dict[str, Any]) -> str:
    reasoning = (
        str(decision.get("reasoning") or "")
        if isinstance(decision, dict)
        else str(decision.reasoning or "")
    )
    import re

    budget_m = re.search(r"可部署买入预算 ¥([\d,]+)", reasoning)
    lot_m = re.search(r"≈ ¥([\d,]+)", reasoning)
    if budget_m and lot_m:
        return (
            f"⚠️ **风控阻断：** 本笔预算 ¥{budget_m.group(1)} 不足一手"
            f"（约 ¥{lot_m.group(1)}），维持观望"
        )
    return TRADE_BLOCK_MESSAGES["buy_budget"]


def format_trade_block_message(decision: TradeDecision | dict[str, Any]) -> Optional[str]:
    block_kind = infer_trade_block_kind(decision)
    if not block_kind:
        return None
    if block_kind == "buy_budget":
        return format_buy_budget_block_message(decision)
    msg = TRADE_BLOCK_MESSAGES.get(block_kind)
    if msg:
        return msg
    if str(block_kind).startswith("sell_"):
        return "⚠️ **风控阻断：** 防御减仓条件未满足，维持观望"
    return TRADE_BLOCK_MESSAGES["buy_verdict"]


def render_intraday_trade_markdown(
    decision: TradeDecision,
    lookback_detail: list[dict[str, Any]],
    report: dict[str, Any],
    scans: list[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
    enriched: Optional[dict[str, Any]] = None,
    audit_only: bool = False,
    skip_reason: Optional[str] = None,
) -> str:
    action_map = {"buy": "买入", "sell": "卖出", "hold": "观望", "skip": "跳过"}
    action_label = action_map.get(decision.action, decision.action)
    if audit_only:
        title = f"**审核摘要 · {action_label}**"
    else:
        title = f"**{decision.trade_id or '调仓评估'} · {action_label}**"
    lines = [
        title,
        "",
        f"**Lookback MSS：** {decision.lookback_mss} 分 · **趋势：** {decision.trend}",
    ]
    if settings is not None and decision.lookback_mss is not None:
        from agent_reach.daily_run.harness_display import format_macro_veto_status_line

        lines.append(format_macro_veto_status_line(decision.lookback_mss, macro_veto_default(settings)))
    lines.append(f"**决策：** {decision.reasoning}")
    if audit_only and skip_reason:
        lines.append(f"ℹ️ **说明：** 本轮未写入调仓序列 — {skip_reason}")
    if decision.friction_blocked:
        lines.append("⚠️ **摩擦惩罚阻断：** 预期收益不足以覆盖佣金与滑点")
    block_message = format_trade_block_message(decision)
    if block_message:
        lines.append(block_message)
    if infer_trade_block_kind(decision) == "buy_budget" and enriched and settings is not None:
        from agent_reach.daily_run.portfolio_manager import buy_budget_footer_markdown
        from agent_reach.daily_run.symbols import build_enriched_symbols

        pf = enriched.get("portfolio") if isinstance(enriched, dict) else {}
        code = str(report.get("code") or enriched.get("code") or "")
        footer = buy_budget_footer_markdown(
            pf or {},
            build_enriched_symbols(enriched),
            settings,
            prefer_code=code,
        )
        if footer:
            lines.append(footer)

    if enriched and (enriched.get("team_review") or enriched.get("expert_results")):
        from agent_reach.daily_run.team import expert_card_enabled, render_team_markdown

        if settings is None or expert_card_enabled(settings, workflow="intraday"):
            team_md = render_team_markdown(enriched)
            if team_md:
                lines.extend(["", team_md])

    lines.extend(["", "**前序扫描回顾：**"])
    for s in scans[-3:]:
        lines.append(f"- {s['scan_id']}: MSS {s.get('mss_final')} · {s.get('verdict')}")

    if lookback_detail:
        lines.extend(["", "**Lookback 权重计算：**"])
        for item in lookback_detail:
            lines.append(
                f"- {item['scan_id']}: {item['mss_final']} × {item['weight']:.0%} = {item['weighted']}"
            )
        if settings is not None:
            from agent_reach.daily_run.harness_display import format_lookback_overlay_markdown

            lookback_md = format_lookback_overlay_markdown(settings)
            if lookback_md:
                lines.append(lookback_md)

    if report.get("invalidation"):
        lines.extend(["", f"**失效条件：** {report['invalidation']}"])
    return "\n".join(lines)


def _harness_overlay_note(settings: dict[str, Any]) -> str:
    from agent_reach.daily_run.harness_display import format_harness_decision_footnote

    return format_harness_decision_footnote(settings)


def _intraday_shanghai_now(
    snapshot: dict[str, Any],
    report: dict[str, Any],
    session_scans: Optional[list[dict[str, Any]]] = None,
) -> Optional[datetime]:
    """Prefer snapshot/report scan time over wall clock for intraday gates."""
    sh = ZoneInfo("Asia/Shanghai")
    for src in (report, snapshot):
        if not isinstance(src, dict):
            continue
        raw = src.get("as_of") or src.get("generated_at")
        if not raw:
            continue
        try:
            text = str(raw).replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(sh)
        except ValueError:
            continue
    for scan in reversed(session_scans or []):
        if not isinstance(scan, dict):
            continue
        raw = scan.get("as_of") or scan.get("at")
        if not raw:
            continue
        try:
            text = str(raw).replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(sh)
        except ValueError:
            continue
    return None


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
    prior_trades: Optional[list[dict[str, Any]]] = None,
    session_scans: Optional[list[dict[str, Any]]] = None,
    hold_debounce_strikes: Optional[dict[str, int]] = None,
) -> TradeDecision:
    trading = settings.get("trading", {})
    macro_veto = macro_veto_default(settings)
    from agent_reach.daily_run.sector_gap_guard import intraday_macro_veto_with_sector_buffer

    macro_veto, sector_gap_note = intraday_macro_veto_with_sector_buffer(
        macro_veto,
        snapshot,
        settings=settings,
    )
    from agent_reach.daily_run.systemic_risk import intraday_macro_veto_systemic_bump

    macro_veto, systemic_note = intraday_macro_veto_systemic_bump(
        macro_veto,
        snapshot,
        settings=settings,
    )
    aggressive = effective_aggressive_entry(
        settings,
        str(report.get("code") or ""),
        aggressive_entry_default(settings),
        macro_veto=macro_veto,
    )
    min_cash = min_cash_ratio_default(settings)

    trade_id = f"T{trade_index}"
    portfolio = snapshot.get("portfolio") or {}
    cash_ratio = portfolio.get("cash_ratio")
    overlay_note = _harness_overlay_note(settings)
    if sector_gap_note:
        overlay_note = f"{overlay_note}{sector_gap_note}"
    if systemic_note:
        overlay_note = f"{overlay_note}{systemic_note}"

    sh_now = _intraday_shanghai_now(snapshot, report, session_scans)
    from agent_reach.daily_run.protections.engine import (
        evaluate_protections,
        protection_block_reason,
        protection_overlay_note,
        record_protection_hits,
    )

    active_protections = evaluate_protections(
        snapshot=snapshot,
        report=report,
        side="buy",
        settings=settings,
        prior_trades=prior_trades,
        session_scans=session_scans,
        now=sh_now,
    )
    active_protections.extend(
        evaluate_protections(
            snapshot=snapshot,
            report=report,
            side="sell",
            settings=settings,
            prior_trades=prior_trades,
            session_scans=session_scans,
            now=sh_now,
        )
    )
    seen_prot: set[str] = set()
    deduped_prot = []
    for lock in active_protections:
        key = f"{lock.protection}:{lock.lock_side}:{lock.code}"
        if key in seen_prot:
            continue
        seen_prot.add(key)
        deduped_prot.append(lock)
    if deduped_prot:
        overlay_note = f"{overlay_note}{protection_overlay_note(deduped_prot)}"

    exp_ret = expected_return_pct
    if exp_ret is None:
        exp_ret = estimate_expected_return(lookback_mss, aggressive, macro_veto, settings)

    friction_blocked = not _passes_friction(exp_ret, settings)
    blocked = verdict.blocked or report.get("blocked", False)

    try:
        from agent_reach.daily_run.pit_guard import pit_guard_block_reason

        pit_block = pit_guard_block_reason(snapshot, settings=settings, job="intraday")
    except Exception:
        pit_block = None
    if pit_block:
        return TradeDecision(
            action="hold",
            trade_id=trade_id,
            lookback_mss=lookback_mss,
            lookback_detail=[],
            trend=trend,
            reasoning=f"{pit_block}{overlay_note}",
            blocked=True,
            block_kind="pit_guard",
            friction_blocked=friction_blocked,
            expected_return_pct=exp_ret,
        )

    try:
        from agent_reach.daily_run.drift_trigger import drift_trade_block_reason

        drift_block = drift_trade_block_reason(report=report, snapshot=snapshot, settings=settings)
    except Exception:
        drift_block = None
    if drift_block:
        return TradeDecision(
            action="hold",
            trade_id=trade_id,
            lookback_mss=lookback_mss,
            lookback_detail=[],
            trend=trend,
            reasoning=f"{drift_block}{overlay_note}",
            blocked=True,
            block_kind="drift_trigger",
            friction_blocked=friction_blocked,
            expected_return_pct=exp_ret,
        )

    from agent_reach.daily_run.watchlist_breakout import evaluate_watchlist_breakout_buy

    breakout = evaluate_watchlist_breakout_buy(
        snapshot=snapshot,
        report=report,
        settings=settings,
        lookback_mss=lookback_mss,
        trend=trend,
        aggressive_entry=aggressive,
        now=_intraday_shanghai_now(snapshot, report, session_scans),
    )
    if breakout.eligible:
        from agent_reach.daily_run.watchlist_breakout import _symbol_change_pct

        chg = _symbol_change_pct(snapshot, str(report.get("code") or ""))
        if chg is not None:
            breakout_exp = max(0.0, float(chg) / 100.0 * 0.35)
            exp_ret = max(float(exp_ret or 0.0), breakout_exp)
            friction_blocked = not _passes_friction(exp_ret, settings)

    audit_block = intraday_audit_block_reason(settings, report)
    if audit_block:
        return TradeDecision(
            action="hold",
            trade_id=trade_id,
            lookback_mss=lookback_mss,
            lookback_detail=[],
            trend=trend,
            reasoning=f"{audit_block}{overlay_note}",
            blocked=True,
            block_kind="audit",
            friction_blocked=friction_blocked,
            expected_return_pct=exp_ret,
        )

    if lookback_mss < macro_veto:
        return TradeDecision(
            action="sell"
            if _decision_symbol_sellable(snapshot, settings, report.get("code"))
            else "hold",
            trade_id=trade_id,
            lookback_mss=lookback_mss,
            lookback_detail=[],
            trend=trend,
            reasoning=f"Lookback MSS {lookback_mss:.0f} 低于否决线 {macro_veto:.0f}，宏观避险{overlay_note}",
            blocked=False,
            friction_blocked=False,
            expected_return_pct=exp_ret,
        )

    if blocked and not breakout.eligible:
        return TradeDecision(
            action="hold",
            trade_id=trade_id,
            lookback_mss=lookback_mss,
            lookback_detail=[],
            trend=trend,
            reasoning=f"标签 {verdict.verdict} 阻断买入（即时 MSS {verdict.mss_final:.0f}）",
            blocked=True,
            block_kind="buy_verdict",
            friction_blocked=friction_blocked,
            expected_return_pct=exp_ret,
        )

    standard_buy = lookback_mss >= aggressive and trend_allows_buy(settings, trend)
    if standard_buy or breakout.eligible:
        from agent_reach.daily_run.protections.sector_mss_mismatch import protection_verdict_cap

        verdict_cap = protection_verdict_cap(
            snapshot=snapshot,
            report=report,
            settings=settings,
        )
        if verdict_cap and str(getattr(verdict, "verdict", "") or report.get("verdict") or "") == "可做":
            prot = protection_block_reason(
                snapshot=snapshot,
                report=report,
                side="buy",
                settings=settings,
                prior_trades=prior_trades,
                session_scans=session_scans,
                now=sh_now,
            )
            if prot is None:
                prot_reason = (
                    f"sector_mss_mismatch：高 MSS 但板块弱于指数，verdict 上限「{verdict_cap}」"
                )
            else:
                prot_reason = prot.reason
            record_protection_hits(
                [prot] if prot else deduped_prot[:1],
                settings=settings,
                code=str(report.get("code") or ""),
            )
            return TradeDecision(
                action="hold",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"{prot_reason}{overlay_note}",
                blocked=True,
                block_kind="protection_buy",
                friction_blocked=friction_blocked,
                expected_return_pct=exp_ret,
            )
        prot_buy = protection_block_reason(
            snapshot=snapshot,
            report=report,
            side="buy",
            settings=settings,
            prior_trades=prior_trades,
            session_scans=session_scans,
            now=sh_now,
        )
        if prot_buy:
            record_protection_hits([prot_buy], settings=settings, code=str(report.get("code") or ""))
            return TradeDecision(
                action="hold",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"{prot_buy.reason}{overlay_note}",
                blocked=True,
                block_kind="protection_buy",
                friction_blocked=friction_blocked,
                expected_return_pct=exp_ret,
            )
    if standard_buy or breakout.eligible:
        buy_block = None
        from agent_reach.daily_run.skill_rejected import trade_blocked_by_rejected

        buy_block = trade_blocked_by_rejected(
            "buy",
            code=str(report.get("code") or ""),
            name=str(report.get("name") or ""),
            settings=settings,
            trend=trend,
        )
        if not buy_block:
            from agent_reach.daily_run.session_overlay import week_open_trade_block

            buy_block = week_open_trade_block(
                settings,
                str(report.get("code") or ""),
                "buy",
            )
        if buy_block:
            return TradeDecision(
                action="hold",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"已证伪策略阻断买入：{buy_block}{overlay_note}"
                if "周日" not in buy_block
                else f"{buy_block}{overlay_note}",
                blocked=True,
                block_kind="buy_rejected" if "周日" not in buy_block else "week_open_plan",
                friction_blocked=friction_blocked,
                expected_return_pct=exp_ret,
            )
        pnl_buy_block = pnl_buy_block_reason(
            settings,
            portfolio,
            code=str(report.get("code") or ""),
        )
        if pnl_buy_block:
            return TradeDecision(
                action="hold",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"{pnl_buy_block}{overlay_note}",
                blocked=True,
                block_kind="buy_pnl",
                friction_blocked=friction_blocked,
                expected_return_pct=exp_ret,
            )
        symbol_code = str(report.get("code") or "")
        ledger_block = pnl_symbol_ledger_block_reason(settings, symbol_code, portfolio)
        if ledger_block:
            return TradeDecision(
                action="hold",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"{ledger_block}{overlay_note}",
                blocked=True,
                block_kind="buy_ledger",
                friction_blocked=friction_blocked,
                expected_return_pct=exp_ret,
            )
        kronos_block = kronos_buy_block_reason(settings, symbol_code)
        if kronos_block:
            return TradeDecision(
                action="hold",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"{kronos_block}{overlay_note}",
                blocked=True,
                block_kind="buy_kronos",
                friction_blocked=friction_blocked,
                expected_return_pct=exp_ret,
            )
        from agent_reach.daily_run.systemic_risk import systemic_buy_block_reason

        systemic_block = systemic_buy_block_reason(
            settings,
            code=symbol_code,
            snapshot=snapshot,
        )
        if systemic_block:
            return TradeDecision(
                action="hold",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"{systemic_block}{overlay_note}",
                blocked=True,
                block_kind="buy_systemic_risk",
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
                block_kind="buy_cash",
                friction_blocked=friction_blocked,
                expected_return_pct=exp_ret,
            )
        deep_loss_block = deep_loss_buy_block_reason(
            prior_trades,
            symbol_code,
            snapshot,
            current_action="buy",
            settings=settings,
        )
        if deep_loss_block:
            return TradeDecision(
                action="buy",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"{deep_loss_block}{overlay_note}",
                blocked=True,
                block_kind="buy_deep_loss",
                friction_blocked=False,
                expected_return_pct=exp_ret,
            )
        from agent_reach.daily_run.portfolio_manager import buy_budget_precheck_reason
        from agent_reach.daily_run.symbols import build_enriched_symbols

        cash_limit_bypass = should_apply_consecutive_buy_cash_bypass(
            prior_trades,
            symbol_code,
            current_action="buy",
            settings=settings,
        )
        max_pos_override = breakout.max_position_pct if breakout.eligible else None
        budget_block = buy_budget_precheck_reason(
            portfolio,
            build_enriched_symbols(snapshot),
            settings,
            prefer_code=symbol_code,
            cash_limit_bypass=cash_limit_bypass,
            max_position_pct_override=max_pos_override,
        )
        if budget_block:
            bypass_note = "；连续买入建议，临时突破 deploy/现金限制" if cash_limit_bypass else ""
            return TradeDecision(
                action="buy",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"{budget_block}{bypass_note}{overlay_note}",
                blocked=True,
                block_kind="buy_budget",
                friction_blocked=False,
                expected_return_pct=exp_ret,
                max_position_pct_override=max_pos_override,
                watchlist_breakout=breakout.eligible,
            )
        if friction_blocked and not breakout.eligible:
            return TradeDecision(
                action="hold",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=(
                    f"MSS 达 {lookback_mss:.0f} 但预期收益 {exp_ret:.2%} 不足以覆盖摩擦成本"
                    f"{overlay_note}"
                ),
                blocked=False,
                friction_blocked=True,
                expected_return_pct=exp_ret,
            )
        buy_reason = (
            f"{breakout.reason}{overlay_note}"
            if breakout.eligible
            else f"Lookback MSS {lookback_mss:.0f} ≥ {aggressive:.0f} 且趋势 {trend}，条件性建仓{overlay_note}"
        )
        return TradeDecision(
            action="buy",
            trade_id=trade_id,
            lookback_mss=lookback_mss,
            lookback_detail=[],
            trend=trend,
            reasoning=buy_reason,
            blocked=False,
            friction_blocked=False,
            expected_return_pct=exp_ret,
            max_position_pct_override=max_pos_override,
            watchlist_breakout=breakout.eligible,
        )

    from agent_reach.daily_run.profit_lock import evaluate_profit_lock_sell

    allow_profit, profit_block, profit_ratio = evaluate_profit_lock_sell(
        settings,
        report=report,
        snapshot=snapshot,
        prior_trades=prior_trades,
        session_scans=session_scans,
    )
    if allow_profit:
        prot_sell = protection_block_reason(
            snapshot=snapshot,
            report=report,
            side="sell",
            settings=settings,
            prior_trades=prior_trades,
            session_scans=session_scans,
            now=sh_now,
        )
        if prot_sell:
            record_protection_hits([prot_sell], settings=settings, code=str(report.get("code") or ""))
            return TradeDecision(
                action="hold",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"{prot_sell.reason}{overlay_note}",
                blocked=True,
                block_kind="protection_sell",
                friction_blocked=False,
                expected_return_pct=exp_ret,
            )
        if _decision_symbol_sellable(snapshot, settings, report.get("code")):
            return TradeDecision(
                action="sell",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"{profit_block}{overlay_note}",
                blocked=False,
                friction_blocked=False,
                expected_return_pct=exp_ret,
                sell_kind="profit_lock",
                sell_ratio_override=profit_ratio,
            )
        deep_loss_reason = _deep_loss_sell_block_reason(snapshot, settings, report.get("code"))
        if deep_loss_reason:
            return TradeDecision(
                action="hold",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"动态止盈信号触发，但{deep_loss_reason}{overlay_note}",
                blocked=True,
                block_kind="sell_deep_loss",
                friction_blocked=False,
                expected_return_pct=exp_ret,
            )
    elif profit_block:
        return TradeDecision(
            action="hold",
            trade_id=trade_id,
            lookback_mss=lookback_mss,
            lookback_detail=[],
            trend=trend,
            reasoning=f"{profit_block}{overlay_note}",
            blocked=True,
            block_kind="sell_profit_lock",
            friction_blocked=False,
            expected_return_pct=exp_ret,
        )

    if _decision_symbol_has_holding(snapshot, report.get("code")):
        runtime = settings.get("harness_runtime") or {}
        trade_signals = runtime.get("trade_signals") or {}
        allow_defensive, defensive_block = evaluate_defensive_trim_sell(
            settings,
            lookback_mss=lookback_mss,
            macro_veto=macro_veto,
            trend=trend,
            trade_signals=trade_signals,
            report=report,
            snapshot=snapshot,
            prior_trades=prior_trades,
        )
        from agent_reach.daily_run.hold_debounce_guards import touch_week_open_hold_debounce

        hold_block: Optional[str] = None
        hold_sell_ratio_cap: Optional[float] = None
        if hold_debounce_strikes is not None:
            hold_block, hold_sell_ratio_cap = touch_week_open_hold_debounce(
                settings,
                str(report.get("code") or ""),
                allow_defensive=allow_defensive,
                strikes=hold_debounce_strikes,
                price=_optional_float(report.get("price")),
            )

        if allow_defensive:
            prot_sell = protection_block_reason(
                snapshot=snapshot,
                report=report,
                side="sell",
                settings=settings,
                prior_trades=prior_trades,
                session_scans=session_scans,
                now=sh_now,
            )
            if prot_sell:
                record_protection_hits(
                    [prot_sell],
                    settings=settings,
                    code=str(report.get("code") or ""),
                )
                return TradeDecision(
                    action="hold",
                    trade_id=trade_id,
                    lookback_mss=lookback_mss,
                    lookback_detail=[],
                    trend=trend,
                    reasoning=f"{prot_sell.reason}{overlay_note}",
                    blocked=True,
                    block_kind="protection_sell",
                    friction_blocked=False,
                    expected_return_pct=exp_ret,
                )
            if hold_block:
                return TradeDecision(
                    action="hold",
                    trade_id=trade_id,
                    lookback_mss=lookback_mss,
                    lookback_detail=[],
                    trend=trend,
                    reasoning=f"{hold_block}{overlay_note}",
                    blocked=True,
                    block_kind="sell_week_open_hold_debounce",
                    friction_blocked=False,
                    expected_return_pct=exp_ret,
                )
            if _decision_symbol_sellable(snapshot, settings, report.get("code")):
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
                    sell_kind="defensive_trim",
                    sell_ratio_override=hold_sell_ratio_cap,
                )
            deep_loss_reason = _deep_loss_sell_block_reason(
                snapshot,
                settings,
                report.get("code"),
                sell_kind="defensive_trim",
            )
            if deep_loss_reason:
                return TradeDecision(
                    action="hold",
                    trade_id=trade_id,
                    lookback_mss=lookback_mss,
                    lookback_detail=[],
                    trend=trend,
                    reasoning=f"防御性减仓信号触发，但{deep_loss_reason}{overlay_note}",
                    blocked=True,
                    block_kind="sell_deep_loss",
                    friction_blocked=False,
                    expected_return_pct=exp_ret,
                )
        elif defensive_block:
            return TradeDecision(
                action="hold",
                trade_id=trade_id,
                lookback_mss=lookback_mss,
                lookback_detail=[],
                trend=trend,
                reasoning=f"{defensive_block}{overlay_note}",
                blocked=True,
                block_kind="sell_defensive_trim",
                friction_blocked=False,
                expected_return_pct=exp_ret,
            )
    elif hold_debounce_strikes is not None:
        from agent_reach.daily_run.snapshot_builder import _normalize_code

        norm = _normalize_code(str(report.get("code") or ""))
        if norm:
            hold_debounce_strikes[norm] = 0

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
    from agent_reach.daily_run.quant_calibration import friction_buy_blocked

    return not friction_buy_blocked(expected_return_pct, settings)


def _holding_locked(snapshot: dict[str, Any], settings: dict[str, Any]) -> bool:
    from agent_reach.daily_run.portfolio_manager import holding_is_sellable

    holdings = (snapshot.get("portfolio") or {}).get("holdings") or []
    if not holdings:
        return False
    return not any(holding_is_sellable(h, settings) for h in holdings)


def _decision_symbol_has_holding(snapshot: dict[str, Any], code: Any) -> bool:
    from agent_reach.daily_run.snapshot_builder import _normalize_code

    target = _normalize_code(str(code or ""))
    if not target:
        return False
    pf = snapshot.get("portfolio") or {}
    for holding in pf.get("holdings") or []:
        if _normalize_code(str(holding.get("code", ""))) == target:
            return True
    return False


def _decision_symbol_sellable(
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    code: Any,
) -> bool:
    from agent_reach.daily_run.portfolio_manager import decision_symbol_sellable

    return decision_symbol_sellable(snapshot, settings, str(code or ""))


def _deep_loss_sell_block_reason(
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    code: Any,
    *,
    sell_kind: Optional[str] = None,
) -> Optional[str]:
    from agent_reach.daily_run.portfolio_manager import deep_loss_sell_block_reason, holding_is_sellable
    from agent_reach.daily_run.symbols import build_enriched_symbols

    target = str(code or "").strip()
    if not target:
        return None
    pf = snapshot.get("portfolio") or {}
    enriched = build_enriched_symbols(snapshot, settings)
    norm = lambda c: str(c).zfill(6)[-6:]
    for holding in pf.get("holdings") or []:
        if norm(holding.get("code", "")) != norm(target):
            continue
        if not holding_is_sellable(holding, settings):
            return None
        return deep_loss_sell_block_reason(
            pf,
            holding,
            enriched,
            settings,
            sell_kind=sell_kind,
        )
    return None


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _today_str() -> str:
    return today_shanghai().isoformat()

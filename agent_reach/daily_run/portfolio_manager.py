# -*- coding: utf-8
"""Paper portfolio auto-adjust based on MSS trade signals."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run import trade_calendar
from agent_reach.daily_run.harness_policy import (
    deep_loss_policy_default,
    friction_commission_rate_default,
    harness_buy_budget,
    min_cash_ratio_default,
    min_deploy_cash_default,
    runtime_int_default,
    runtime_float_default,
)
from agent_reach.daily_run.pnl_execution_guard import (
    pnl_buy_block_reason,
    pnl_symbol_ledger_block_reason,
)
from agent_reach.daily_run.settings import effective_settings
from agent_reach.daily_run.snapshot_builder import _normalize_code
from agent_reach.daily_run.symbols import build_enriched_symbols, copy_portfolio


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _symbol_turnover_cny(enriched_row: Optional[dict[str, Any]]) -> Optional[float]:
    if not enriched_row:
        return None
    return _optional_float(enriched_row.get("turnover"))


def _trade_deploy_budget_kwargs(
    code: str,
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
) -> dict[str, Any]:
    row = enriched.get(_normalize_code(code)) or enriched.get(code) or {}
    turnover = _symbol_turnover_cny(row)
    if turnover is None:
        return {}
    try:
        from agent_reach.daily_run.harness_reading_signals import resolve_harness_reading_signals

        reading = resolve_harness_reading_signals(settings)
        trend = str(reading.get("trend") or "")
        return {
            "turnover_cny": turnover,
            "mss_delta": reading.get("delta_from_low"),
            "trend_confirmed": trend in {"rising", "turning_up"} or bool(reading.get("mss_recovery")),
        }
    except Exception:
        return {"turnover_cny": turnover}


@dataclass
class TradeAction:
    side: str  # buy | sell
    code: str
    name: str
    shares: int
    price: float
    amount: float
    commission: float
    reasoning: str
    holding_cost: Optional[float] = None
    order_state: str = "complete"
    fill_timing: str = ""
    slippage_rate: Optional[float] = None
    volume_limited: bool = False
    oco_group_id: str = ""
    reject_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "side": self.side,
            "code": self.code,
            "name": self.name,
            "shares": self.shares,
            "price": self.price,
            "amount": self.amount,
            "commission": self.commission,
            "reasoning": self.reasoning,
            "order_state": self.order_state,
        }
        if self.holding_cost is not None and float(self.holding_cost) > 0:
            payload["holding_cost"] = round(float(self.holding_cost), 4)
        if self.fill_timing:
            payload["fill_timing"] = self.fill_timing
        if self.slippage_rate is not None:
            payload["slippage_rate"] = self.slippage_rate
        if self.volume_limited:
            payload["volume_limited"] = True
        if self.oco_group_id:
            payload["oco_group_id"] = self.oco_group_id
        if self.reject_reason:
            payload["reject_reason"] = self.reject_reason
        return payload


@dataclass
class ApplyResult:
    applied: bool
    portfolio: dict[str, Any]
    actions: list[TradeAction] = field(default_factory=list)
    message: str = ""
    action_payloads: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payloads = self.action_payloads or [a.to_dict() for a in self.actions]
        return {
            "applied": self.applied,
            "message": self.message,
            "actions": payloads,
        }


def default_ledger_path() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "trade_ledger.jsonl"


def daily_trade_state_path() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "daily_trade_state.json"


def _today_str() -> str:
    return trade_calendar.today_shanghai().isoformat()


def _actions_fingerprint(actions: list[TradeAction]) -> str:
    parts: list[str] = []
    for action in actions:
        parts.append(
            "|".join(
                [
                    str(action.side),
                    _normalize_code(str(action.code)),
                    str(int(action.shares)),
                    f"{float(action.price):.4f}",
                    f"{float(action.amount):.2f}",
                ]
            )
        )
    return "||".join(sorted(parts))


def ledger_entry_fingerprint(entry: dict[str, Any]) -> str:
    day = str(entry.get("at") or "")[:10]
    parts: list[str] = []
    for action in entry.get("actions") or []:
        parts.append(
            "|".join(
                [
                    str(action.get("side") or ""),
                    _normalize_code(str(action.get("code") or "")),
                    str(int(action.get("shares") or 0)),
                    f"{float(action.get('price') or 0):.4f}",
                    f"{float(action.get('amount') or 0):.2f}",
                ]
            )
        )
    return f"{day}::" + "||".join(sorted(parts))


def dedupe_trade_ledger_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop repeated ledger rows (same day + same action payload)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for entry in entries:
        fp = ledger_entry_fingerprint(entry)
        if fp in seen:
            continue
        seen.add(fp)
        out.append(entry)
    return out


def load_daily_trade_state(*, settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    path = daily_trade_state_path()
    try:
        from agent_reach.daily_run.storage.config import storage_db_reads_allowed
        from agent_reach.daily_run.storage.readers import read_daily_trade_state

        if storage_db_reads_allowed(settings, file_path=path):
            from agent_reach.daily_run.settings import load_settings

            cfg = settings or load_settings()
            db_state = read_daily_trade_state(settings=cfg)
            if isinstance(db_state, dict) and db_state.get("date") == _today_str():
                db_state.setdefault("fingerprints", [])
                return db_state
    except Exception:
        pass
    if not path.exists():
        return {"date": _today_str(), "fingerprints": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"date": _today_str(), "fingerprints": []}
    if data.get("date") != _today_str():
        return {"date": _today_str(), "fingerprints": []}
    data.setdefault("fingerprints", [])
    return data


def save_daily_trade_state(state: dict[str, Any]) -> None:
    path = daily_trade_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        from agent_reach.daily_run.storage.hooks import on_l1_state

        on_l1_state("daily_trade_state", "daily_trade_state", state)
    except Exception:
        pass


def global_trades_today() -> int:
    return len(load_daily_trade_state().get("fingerprints") or [])


def _fingerprint_codes(fingerprint: str) -> set[str]:
    """Extract normalized symbol codes out of an _actions_fingerprint string."""
    codes: set[str] = set()
    for part in fingerprint.split("||"):
        segs = part.split("|")
        if len(segs) >= 2 and segs[1]:
            codes.add(segs[1])
    return codes


def symbol_trades_today(code: str) -> int:
    """Applied (buy/sell) trade count today for one symbol, across all fingerprints."""
    norm = _normalize_code(str(code))
    if not norm:
        return 0
    state = load_daily_trade_state()
    return sum(1 for fp in state.get("fingerprints") or [] if norm in _fingerprint_codes(fp))


def applied_trades_today_for(code: str, settings: dict[str, Any]) -> int:
    """Applied-trade count today, scoped by schedule.max_applied_trades_per_day_scope.

    Default scope is "global" (the historical/default behavior: one shared cap
    across the whole portfolio). Set to "per_symbol" to give every symbol its own
    daily cap instead — useful when symbols_mode="all" runs many symbols in
    parallel and a single global cap can starve later symbols of any chance to
    apply a valid signal.
    """
    scope = str((settings.get("schedule") or {}).get("max_applied_trades_per_day_scope") or "global").strip().lower()
    if scope == "per_symbol" and code:
        return symbol_trades_today(code)
    return global_trades_today()


def register_applied_trade(actions: list[TradeAction]) -> bool:
    """Record a successful paper trade for today. Returns False if duplicate."""
    if not actions:
        return False
    fp = _actions_fingerprint(actions)
    state = load_daily_trade_state()
    fingerprints = list(state.get("fingerprints") or [])
    if fp in fingerprints:
        return False
    fingerprints.append(fp)
    state["date"] = _today_str()
    state["fingerprints"] = fingerprints
    save_daily_trade_state(state)
    return True


def portfolio_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return settings.get("portfolio") or {}


def is_auto_adjust_enabled(settings: dict[str, Any]) -> bool:
    return bool(portfolio_settings(settings).get("auto_adjust_enabled", False))


def max_total_symbols(settings: dict[str, Any]) -> int:
    """持仓 + 观察池（去重）合计上限。"""
    pf = portfolio_settings(settings)
    if "max_total_symbols" in pf:
        return int(pf["max_total_symbols"])
    return runtime_int_default(settings, "portfolio", "max_total_symbols")


def max_holdings(settings: dict[str, Any]) -> int:
    """Max distinct held symbols (portfolio.max_holdings)."""
    pf = portfolio_settings(settings)
    return runtime_int_default(settings, "portfolio", "max_holdings")


def unique_symbol_codes(portfolio: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for h in portfolio.get("holdings") or []:
        code = _normalize_code(str(h.get("code", "")))
        if code:
            codes.add(code)
    for w in portfolio.get("watchlist") or []:
        code = _normalize_code(str(w.get("code", "")))
        if code:
            codes.add(code)
    return codes


def unique_symbol_count(portfolio: dict[str, Any]) -> int:
    return len(unique_symbol_codes(portfolio))


def watchlist_capacity(settings: dict[str, Any], portfolio: dict[str, Any]) -> int:
    """观察池可再容纳的非持仓标的数（在合计上限内）。"""
    held = {
        _normalize_code(str(h.get("code", "")))
        for h in portfolio.get("holdings") or []
        if _normalize_code(str(h.get("code", "")))
    }
    return max(0, max_total_symbols(settings) - len(held))


def append_trade_ledger(
    actions: list[TradeAction],
    *,
    trade_id: Optional[str] = None,
    decision_action: Optional[str] = None,
    path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Append ledger row; return enriched action dicts (incl. FIFO realized_pnl on sells)."""
    if not actions:
        return []
    p = path or default_ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    at = datetime.now(timezone.utc).isoformat()
    raw_actions = [a.to_dict() for a in actions]
    from agent_reach.daily_run.realized_pnl import (
        enrich_sell_actions,
        load_ledger_entries,
        opening_costs_from_portfolio,
    )
    from agent_reach.daily_run.snapshot_builder import load_portfolio

    prior = load_ledger_entries(path=p, end=trade_calendar.today_shanghai())
    opening_costs = opening_costs_from_portfolio(load_portfolio())
    try:
        from agent_reach.daily_run.workflows import load_morning_baseline

        morning_costs = opening_costs_from_portfolio(
            (load_morning_baseline().get("portfolio") or {})
        )
        merged = dict(morning_costs)
        for code, cost in opening_costs.items():
            merged.setdefault(code, cost)
        opening_costs = merged
    except FileNotFoundError:
        pass
    enriched = enrich_sell_actions(
        prior,
        raw_actions,
        entry_at=at,
        trade_id=trade_id,
        opening_costs=opening_costs or None,
    )
    entry = {
        "at": at,
        "trade_id": trade_id,
        "decision_action": decision_action,
        "actions": enriched,
    }
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    try:
        from agent_reach.daily_run.storage.hooks import on_trade_ledger

        on_trade_ledger(entry, source_path=str(p))
    except Exception:
        pass
    return enriched


def holding_today_buy_shares(holding: dict[str, Any]) -> int:
    """Shares bought on the current trade session (A-share T+1 lock)."""
    return max(0, int(holding.get("today_buy_shares") or 0))


def holding_sellable_shares(holding: dict[str, Any]) -> int:
    """Shares eligible to sell today (total minus same-session buys)."""
    total = int(holding.get("shares") or 0)
    locked = holding_today_buy_shares(holding)
    return max(0, total - locked)


def _reset_today_buys_for_new_session(pf: dict[str, Any]) -> dict[str, Any]:
    """Clear today_buy_shares when portfolio trade session rolls to a new day."""
    today = _today_str()
    if str(pf.get("trade_session_date") or "") == today:
        return pf
    out = dict(pf)
    out["trade_session_date"] = today
    holdings: list[dict[str, Any]] = []
    for h in pf.get("holdings") or []:
        row = dict(h)
        if holding_today_buy_shares(row) > 0:
            row["today_buy_shares"] = 0
        holdings.append(row)
    out["holdings"] = holdings
    return out


def effective_days_held(
    holding: dict[str, Any],
    *,
    as_of: Optional[date] = None,
    settings: Optional[dict[str, Any]] = None,
) -> int:
    """Prefer acquired_date (T+1 calendar) over stale days_held counter."""
    acquired = holding.get("acquired_date")
    if acquired:
        try:
            start = date.fromisoformat(str(acquired)[:10])
            as_of = as_of or trade_calendar.today_shanghai()
            return trade_calendar.trading_days_held(start, as_of, settings=settings)
        except ValueError:
            pass
    return int(holding.get("days_held") or 0)


def holding_is_sellable(
    holding: dict[str, Any],
    settings: dict[str, Any],
    *,
    as_of: Optional[date] = None,
) -> bool:
    total = int(holding.get("shares") or 0)
    if total <= 0:
        return False
    if holding_sellable_shares(holding) <= 0:
        return False
    lock_days = runtime_int_default(settings, "trading", "holding_lock_days")
    return effective_days_held(holding, as_of=as_of, settings=settings) >= lock_days


def _pnl_overview_cfg(settings: dict[str, Any]) -> dict[str, Any]:
    return dict(settings.get("pnl_overview") or {})


def deep_loss_policy(settings: dict[str, Any]) -> dict[str, float]:
    from agent_reach.daily_run.harness_policy import _deep_loss_policy

    return _deep_loss_policy(settings)


def _holding_unrealized_pnl(
    holding: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
) -> tuple[float, Optional[float]]:
    code = _normalize_code(str(holding.get("code", "")))
    row = {**holding, **enriched.get(code, {})}
    shares = int(row.get("shares") or 0)
    cost = float(row.get("cost") or 0)
    price = _price_for(row, enriched) or cost
    cost_basis = shares * cost
    if cost_basis <= 0:
        return 0.0, None
    unrealized = round(shares * price - cost_basis, 2)
    pct = round(unrealized / cost_basis * 100, 2)
    return unrealized, pct


def is_deep_loss_holding(
    holding: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
) -> bool:
    """True when unrealized loss exceeds harness-evolved deep-loss thresholds."""
    unrealized, pct = _holding_unrealized_pnl(holding, enriched)
    if unrealized >= -0.01:
        return False
    loss_abs = abs(unrealized)
    loss_cny_thr = deep_loss_policy_default(settings, "loss_cny_threshold")
    loss_pct_thr = deep_loss_policy_default(settings, "loss_pct_threshold")
    if loss_abs >= loss_cny_thr:
        return True
    return pct is not None and abs(pct) >= loss_pct_thr


def resolve_deep_loss_sell_shares(
    total_shares: int,
    code: str,
    settings: dict[str, Any],
    *,
    is_deep_loss: bool,
    sell_ratio_override: Optional[float] = None,
) -> int:
    """Shares to sell using harness-evolved sell_ratio (deep vs non-deep)."""
    if total_shares <= 0:
        return 0
    ratio_key = "sell_ratio" if is_deep_loss else "non_deep_loss_sell_ratio"
    ratio = (
        float(sell_ratio_override)
        if sell_ratio_override is not None
        else deep_loss_policy_default(settings, ratio_key)
    )
    if ratio >= 0.999:
        return total_shares
    sold = _round_lot(code, int(total_shares * ratio), total_shares=total_shares)
    if sold <= 0:
        return 0
    return min(sold, total_shares)


def deep_loss_sell_analysis(
    pf: dict[str, Any],
    holding: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
    *,
    sell_kind: Optional[str] = None,
) -> dict[str, Any]:
    """Harness deep-loss sell gate: thresholds, cover requirement, sell ratio."""
    policy = deep_loss_policy(settings)
    unrealized, pct = _holding_unrealized_pnl(holding, enriched)
    deep = is_deep_loss_holding(holding, enriched, settings)
    loss_abs = abs(unrealized) if unrealized < -0.01 else 0.0
    cover_ratio = float(policy.get("cover_ratio", 1.0))
    code = _normalize_code(str(holding.get("code") or ""))
    from agent_reach.daily_run.deep_loss_cover_policy import cover_exempt_for_sell

    if cover_exempt_for_sell(code, settings=settings, sell_kind=sell_kind):
        cover_ratio = 0.0
    from agent_reach.daily_run.session_regime import supportive_regime_active

    supportive_reallocation = False
    if deep and supportive_regime_active(settings):
        supportive_reallocation = True
        reallocation_cover = float(
            policy.get(
                "supportive_reallocation_cover_ratio",
                policy.get("supportive_cover_ratio", 0.35),
            )
        )
        cover_ratio = min(cover_ratio, max(0.0, reallocation_cover))
    coverable = portfolio_coverable_gains(
        pf,
        enriched,
        settings,
        exclude_code=str(holding.get("code") or ""),
    )
    required_cover = round(loss_abs * cover_ratio, 2) if deep and cover_ratio > 0 else 0.0
    total_shares = int(holding.get("shares") or 0)
    sellable = holding_sellable_shares(holding)
    sell_shares = resolve_deep_loss_sell_shares(
        min(total_shares, sellable),
        code,
        settings,
        is_deep_loss=deep,
    )
    ratio_key = "sell_ratio" if deep else "non_deep_loss_sell_ratio"
    effective_sell_ratio = float(policy.get(ratio_key, deep_loss_policy_default(settings, ratio_key)))
    if supportive_reallocation:
        reallocation_sell = float(policy.get("supportive_reallocation_sell_ratio", 0.1))
        if reallocation_sell > 0:
            effective_sell_ratio = max(
                effective_sell_ratio,
                min(1.0, reallocation_sell),
            )
    runtime = settings.get("harness_runtime") or {}
    if runtime.get("trade_signals", {}).get("defensive_trim"):
        from agent_reach.daily_run.defensive_trim_guards import defensive_trim_effective_sell_ratio

        effective_sell_ratio = defensive_trim_effective_sell_ratio(
            settings,
            holding,
            is_deep_loss=deep,
            base_ratio=effective_sell_ratio,
        )
        sell_shares = resolve_deep_loss_sell_shares(
            min(total_shares, sellable),
            code,
            settings,
            is_deep_loss=deep,
            sell_ratio_override=effective_sell_ratio,
        )
    allowed = True
    block_reason: Optional[str] = None
    if deep and cover_ratio > 0 and loss_abs > 0 and coverable < required_cover:
        allowed = False
        name = holding.get("name") or code or "?"
        pct_part = f" / {abs(pct):.1f}%" if pct is not None else ""
        block_reason = (
            f"{name} 深度套牢（浮亏 ¥{loss_abs:,.0f}{pct_part}），"
            f"需覆盖 ¥{required_cover:,.0f}（cover_ratio={cover_ratio:.0%}），"
            f"组合可覆盖收益 ¥{coverable:,.0f} 不足，暂不卖"
        )
    elif sell_shares <= 0:
        allowed = False
        name = holding.get("name") or code or "?"
        if deep:
            block_reason = (
                f"{name} 深度套牢，sell_ratio={effective_sell_ratio:.0%} 不足一手，暂不卖"
            )
        else:
            block_reason = (
                f"{name} 非深亏减仓，non_deep_loss_sell_ratio={effective_sell_ratio:.0%} 不足一手，暂不卖"
            )
    return {
        "is_deep_loss": deep,
        "loss_abs": loss_abs,
        "coverable": coverable,
        "required_cover": required_cover,
        "cover_ratio": cover_ratio,
        "sell_ratio": effective_sell_ratio,
        "sell_shares": sell_shares,
        "allowed": allowed,
        "block_reason": block_reason,
        "policy": policy,
    }


def deep_loss_sell_block_reason(
    pf: dict[str, Any],
    holding: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
    *,
    sell_kind: Optional[str] = None,
) -> Optional[str]:
    """Return block message when harness deep-loss sell conditions fail."""
    return deep_loss_sell_analysis(
        pf,
        holding,
        enriched,
        settings,
        sell_kind=sell_kind,
    ).get("block_reason")


def portfolio_coverable_gains(
    pf: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
    *,
    exclude_code: str,
) -> float:
    """Positive unrealized from other holdings + positive cumulative realized PnL."""
    exclude = _normalize_code(exclude_code)
    coverable = 0.0
    for holding in pf.get("holdings") or []:
        code = _normalize_code(str(holding.get("code", "")))
        if code == exclude:
            continue
        unrealized, _ = _holding_unrealized_pnl(holding, enriched)
        if unrealized > 0:
            coverable += unrealized

    from agent_reach.daily_run.realized_pnl import compute_realized_pnl, load_ledger_entries

    realized = compute_realized_pnl(load_ledger_entries())
    if realized > 0:
        weight = deep_loss_policy_default(settings, "coverable_realized_weight")
        coverable += realized * max(0.0, min(1.0, weight))
    return round(coverable, 2)


def decision_symbol_sellable(
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    code: str,
    *,
    as_of: Optional[date] = None,
    enriched: Optional[dict[str, dict[str, Any]]] = None,
) -> bool:
    """True when the decision symbol is held, past lock, and deep-loss cover check passes."""
    target = _normalize_code(str(code or ""))
    if not target:
        return False
    pf = snapshot.get("portfolio") or {}
    symbol_enriched = enriched if enriched is not None else build_enriched_symbols(snapshot, settings)
    for holding in pf.get("holdings") or []:
        if _normalize_code(str(holding.get("code", ""))) != target:
            continue
        if not holding_is_sellable(holding, settings, as_of=as_of):
            return False
        if pnl_symbol_ledger_block_reason(settings, target, pf):
            return False
        return deep_loss_sell_block_reason(pf, holding, symbol_enriched, settings) is None
    return False


def symbol_is_deep_loss_holding(
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    code: str,
) -> bool:
    """True when the snapshot symbol is held and meets deep-loss thresholds."""
    target = _normalize_code(str(code or ""))
    if not target:
        return False
    pf = snapshot.get("portfolio") or {}
    enriched = build_enriched_symbols(snapshot, settings)
    for holding in pf.get("holdings") or []:
        if _normalize_code(str(holding.get("code") or "")) != target:
            continue
        if int(holding.get("shares") or 0) <= 0:
            return False
        return is_deep_loss_holding(holding, enriched, settings)
    return False


def sync_portfolio_holding_days(
    portfolio: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Refresh days_held and roll same-day buy locks on a new trade session."""
    pf = _reset_today_buys_for_new_session(dict(portfolio))
    holdings = []
    for h in pf.get("holdings") or []:
        row = dict(h)
        row["days_held"] = effective_days_held(row, settings=settings)
        holdings.append(row)
    pf["holdings"] = holdings
    return pf


def increment_holding_days(portfolio: dict[str, Any]) -> dict[str, Any]:
    """Legacy counter bump; prefer sync_portfolio_holding_days from acquired_date."""
    return sync_portfolio_holding_days(portfolio)


def apply_auto_adjust(
    portfolio: dict[str, Any],
    decision: Any,
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    *,
    allow_watchlist_changes: bool = False,
    cash_limit_bypass: bool = False,
) -> ApplyResult:
    """Apply paper buy/sell to portfolio.json based on intraday TradeDecision.

    Watchlist membership is NOT changed here by default — only morning/close
    via watchlist_manager.adjust_watchlist().
    """
    if not is_auto_adjust_enabled(settings):
        return ApplyResult(applied=False, portfolio=portfolio, message="auto_adjust 未启用")

    settings = effective_settings(settings)

    from agent_reach.daily_run.indicator_warmup import indicator_warmup_block_reason

    warmup_reason = indicator_warmup_block_reason(snapshot, settings=settings)
    if warmup_reason:
        return ApplyResult(applied=False, portfolio=portfolio, message=warmup_reason)

    action = getattr(decision, "action", None) or (decision.get("action") if isinstance(decision, dict) else None)
    blocked = getattr(decision, "blocked", False) if not isinstance(decision, dict) else decision.get("blocked", False)
    friction_blocked = (
        getattr(decision, "friction_blocked", False)
        if not isinstance(decision, dict)
        else decision.get("friction_blocked", False)
    )

    if action in (None, "hold", "skip"):
        return ApplyResult(applied=False, portfolio=portfolio, message=f"决策 {action}，不调仓")

    if action == "buy" and (blocked or friction_blocked):
        reasoning = (
            getattr(decision, "reasoning", None)
            if not isinstance(decision, dict)
            else decision.get("reasoning")
        )
        message = str(reasoning or "买入信号被风控或摩擦成本阻断")
        return ApplyResult(applied=False, portfolio=portfolio, message=message)

    pf = sync_portfolio_holding_days(copy_portfolio(portfolio), settings=settings)
    enriched = build_enriched_symbols(snapshot)

    if action == "sell":
        prefer_code = _normalize_code(str(snapshot.get("code") or ""))
        return _apply_sell(
            pf,
            enriched,
            settings,
            decision,
            allow_watchlist_changes=allow_watchlist_changes,
            prefer_code=prefer_code or None,
        )
    if action == "buy":
        prefer_code = _normalize_code(str(snapshot.get("code") or ""))
        max_position_pct_override = (
            getattr(decision, "max_position_pct_override", None)
            if not isinstance(decision, dict)
            else decision.get("max_position_pct_override")
        )
        return _apply_buy(
            pf,
            enriched,
            settings,
            allow_watchlist_changes=allow_watchlist_changes,
            prefer_code=prefer_code or None,
            cash_limit_bypass=cash_limit_bypass,
            max_position_pct_override=max_position_pct_override,
        )

    return ApplyResult(applied=False, portfolio=portfolio, message=f"未知决策 {action}")


def _sell_oco_group_id(sell_kind: Optional[str], sell_analysis: dict[str, Any]) -> str:
    """Map partial/defensive sells to OCO-style group ids (Backtrader bracket semantics)."""
    ratio = float(sell_analysis.get("sell_ratio") or 1.0)
    if sell_kind == "profit_lock":
        return "profit_lock_bracket"
    if sell_kind == "defensive_trim":
        return "defensive_trim_bracket"
    if ratio < 0.999 and sell_analysis.get("is_deep_loss"):
        return "deep_loss_partial_oco"
    if ratio < 0.999:
        return "partial_sell_oco"
    return ""


def _apply_sell(
    pf: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
    decision: Any,
    *,
    allow_watchlist_changes: bool = False,
    prefer_code: Optional[str] = None,
) -> ApplyResult:
    holdings = list(pf.get("holdings") or [])
    if not holdings:
        return ApplyResult(applied=False, portfolio=pf, message="无持仓可卖")

    lock_days = runtime_int_default(settings, "trading", "holding_lock_days")
    code = _normalize_code(str(prefer_code or ""))
    if not code:
        return ApplyResult(applied=False, portfolio=pf, message="卖出决策缺少标的代码")

    target = None
    for h in holdings:
        if _normalize_code(str(h.get("code", ""))) == code:
            target = dict(h)
            break

    if target is None:
        return ApplyResult(applied=False, portfolio=pf, message=f"{code} 不在持仓中，跳过卖出")

    target.update(enriched.get(code, {}))

    from agent_reach.daily_run.tradability import tradability_block_reason

    block_reason = tradability_block_reason(target, side="sell", code=code)
    if block_reason:
        return ApplyResult(applied=False, portfolio=pf, message=block_reason)

    total_shares = int(target.get("shares") or 0)
    sellable = holding_sellable_shares(target)
    if sellable <= 0:
        locked = holding_today_buy_shares(target)
        if locked > 0:
            return ApplyResult(
                applied=False,
                portfolio=pf,
                message=f"{code} 当日买入 {locked} 股 T+1 锁仓，可卖 0 股",
            )
        return ApplyResult(applied=False, portfolio=pf, message=f"{code} 在 {lock_days} 天锁定期内，无法卖出")

    if not holding_is_sellable(target, settings):
        return ApplyResult(applied=False, portfolio=pf, message=f"{code} 在 {lock_days} 天锁定期内，无法卖出")

    ledger_block = pnl_symbol_ledger_block_reason(settings, code, pf)
    if ledger_block:
        return ApplyResult(applied=False, portfolio=pf, message=ledger_block)

    sell_ratio_override = None
    sell_kind = None
    if hasattr(decision, "sell_ratio_override"):
        sell_ratio_override = getattr(decision, "sell_ratio_override", None)
        sell_kind = getattr(decision, "sell_kind", None)
    elif isinstance(decision, dict):
        sell_ratio_override = decision.get("sell_ratio_override")
        sell_kind = decision.get("sell_kind")

    sell_analysis = deep_loss_sell_analysis(
        pf,
        target,
        enriched,
        settings,
        sell_kind=sell_kind,
    )
    if not sell_analysis["allowed"]:
        return ApplyResult(applied=False, portfolio=pf, message=str(sell_analysis["block_reason"]))

    from agent_reach.daily_run.deploy_signal_policy import low_liquidity_trim_blocked

    total_nav = float(pf.get("total") or 0)
    if total_nav <= 0:
        total_nav = float(pf.get("cash") or 0) + _holdings_market_value(holdings, enriched)
    current_weight = 0.0
    if total_nav > 0:
        px = _optional_float(_price_for(target, enriched)) or _optional_float(target.get("price"))
        shares_total = int(target.get("shares") or 0)
        if px and shares_total:
            current_weight = shares_total * px / total_nav * 100.0
    sell_ratio_est = float(sell_analysis.get("sell_ratio") or 0.0)
    target_weight = current_weight * max(0.0, 1.0 - sell_ratio_est)
    trim_block = low_liquidity_trim_blocked(
        current_weight_pct=current_weight,
        target_weight_pct=target_weight,
        turnover_cny=_symbol_turnover_cny(enriched.get(code)),
        settings=settings,
    )
    if trim_block:
        return ApplyResult(applied=False, portfolio=pf, message=trim_block)

    if sell_kind == "profit_lock" and sell_ratio_override is not None:
        from agent_reach.daily_run.profit_lock import profit_lock_effective_sell_ratio

        effective_ratio = profit_lock_effective_sell_ratio(
            settings,
            base_ratio=float(sell_analysis.get("sell_ratio") or 1.0),
            sell_ratio_override=sell_ratio_override,
        )
        code_norm = _normalize_code(str(target.get("code") or ""))
        sell_shares = resolve_deep_loss_sell_shares(
            min(int(target.get("shares") or 0), sellable),
            code_norm,
            settings,
            is_deep_loss=bool(sell_analysis.get("is_deep_loss")),
            sell_ratio_override=effective_ratio,
        )
        sell_analysis = {**sell_analysis, "sell_ratio": effective_ratio, "sell_shares": sell_shares}
    elif sell_kind == "defensive_trim" and sell_ratio_override is not None:
        capped = min(float(sell_analysis.get("sell_ratio") or 1.0), float(sell_ratio_override))
        code_norm = _normalize_code(str(target.get("code") or ""))
        sell_shares = resolve_deep_loss_sell_shares(
            min(int(target.get("shares") or 0), sellable),
            code_norm,
            settings,
            is_deep_loss=bool(sell_analysis.get("is_deep_loss")),
            sell_ratio_override=capped,
        )
        sell_analysis = {**sell_analysis, "sell_ratio": capped, "sell_shares": sell_shares}

    shares = min(int(sell_analysis["sell_shares"] or 0), sellable)
    # Ceiling for lot rounding is `sellable`, not the raw holding total: T+1-locked
    # shares (today_buy_shares) must never be pulled in when rounding a partial
    # sell up to one lot.
    shares = _round_lot(code, shares, total_shares=sellable)
    from agent_reach.daily_run.execution_sim import sim_execution_price, sim_trade_shares

    shares, volume_meta = sim_trade_shares(shares, target, enriched, side="sell", settings=settings)
    price, exec_meta = sim_execution_price(target, enriched, side="sell", settings=settings)
    if shares <= 0 or price is None or price <= 0:
        if holding_today_buy_shares(target) > 0:
            return ApplyResult(
                applied=False,
                portfolio=pf,
                message=f"{code} 当日买入 T+1 锁仓，可卖 {sellable} 股不足一手",
            )
        return ApplyResult(applied=False, portfolio=pf, message=f"{code} 无法卖出（股数或价格无效）")

    commission_rate = friction_commission_rate_default(settings)
    gross = shares * price
    commission = round(gross * commission_rate, 2)
    proceeds = gross - commission

    if shares >= total_shares:
        pf["holdings"] = [h for h in holdings if _normalize_code(str(h.get("code", ""))) != code]
    else:
        updated: list[dict[str, Any]] = []
        for h in holdings:
            if _normalize_code(str(h.get("code", ""))) != code:
                updated.append(h)
                continue
            row = dict(h)
            row["shares"] = total_shares - shares
            updated.append(row)
        pf["holdings"] = updated
    pf["cash"] = round(float(pf.get("cash") or 0) + proceeds, 2)

    if allow_watchlist_changes and portfolio_settings(settings).get("add_sold_to_watchlist", True):
        watchlist = list(pf.get("watchlist") or [])
        codes = {_normalize_code(str(w.get("code", ""))) for w in watchlist}
        if shares >= total_shares and code not in codes and unique_symbol_count(pf) < max_total_symbols(settings):
            watchlist.append({"code": code, "name": target.get("name", code)})
            pf["watchlist"] = watchlist

    sell_note = ""
    sell_ratio = float(sell_analysis.get("sell_ratio") or 1.0)
    if sell_kind == "profit_lock" and sell_ratio < 0.999:
        sell_note = f"（动态止盈 sell_ratio={sell_ratio:.0%}）"
    elif sell_ratio < 0.999:
        label = "深度套牢分批" if sell_analysis.get("is_deep_loss") else "非深亏分批"
        sell_note = f"（{label} sell_ratio={sell_ratio:.0%}）"
    holding_cost = float(target.get("cost") or 0)
    if holding_cost <= 0:
        try:
            from agent_reach.daily_run.workflows import load_morning_baseline

            morning = load_morning_baseline()
            for h in (morning.get("portfolio") or {}).get("holdings") or []:
                if _normalize_code(str(h.get("code", ""))) == code:
                    holding_cost = float(h.get("cost") or 0)
                    break
        except FileNotFoundError:
            pass
    trade = TradeAction(
        side="sell",
        code=code,
        name=str(target.get("name", code)),
        shares=shares,
        price=price,
        amount=round(gross, 2),
        commission=commission,
        reasoning=_decision_reason(decision, f"卖出 {target.get('name', code)} {shares} 股{sell_note}"),
        holding_cost=holding_cost if holding_cost > 0 else None,
        fill_timing=str(exec_meta.get("fill_timing") or ""),
        slippage_rate=exec_meta.get("slippage_rate"),
        volume_limited=bool(volume_meta.get("volume_limited")),
        oco_group_id=_sell_oco_group_id(sell_kind, sell_analysis),
    )
    _recalc_totals(pf, enriched)
    return ApplyResult(applied=True, portfolio=pf, actions=[trade], message=trade.reasoning)


def _apply_buy(
    pf: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
    *,
    allow_watchlist_changes: bool = False,
    prefer_code: Optional[str] = None,
    cash_limit_bypass: bool = False,
    max_position_pct_override: Optional[float] = None,
) -> ApplyResult:
    holdings = list(pf.get("holdings") or [])
    held_codes = {_normalize_code(str(h.get("code", ""))) for h in holdings}
    prefer = _normalize_code(str(prefer_code or ""))

    budget_ctx = _buy_budget_context(
        pf,
        enriched,
        settings,
        holdings,
        cash_limit_bypass=cash_limit_bypass,
    )
    if isinstance(budget_ctx, ApplyResult):
        return budget_ctx
    total, cash, deployable, min_deploy, min_cash_ratio, commission_rate = budget_ctx

    target, resolve_err = _resolve_single_buy_target(prefer, pf, enriched)
    if resolve_err:
        return ApplyResult(applied=False, portfolio=pf, message=resolve_err)
    assert target is not None

    code = _normalize_code(str(target["code"]))

    if code not in held_codes and unique_symbol_count(pf) >= max_total_symbols(settings):
        max_t = max_total_symbols(settings)
        return ApplyResult(
            applied=False,
            portfolio=pf,
            message=f"持仓+观察池已达合计上限 {max_t} 只",
        )

    from agent_reach.daily_run.tradability import tradability_block_reason

    tradability_block = tradability_block_reason(target, side="buy", code=code)
    if tradability_block:
        return ApplyResult(applied=False, portfolio=pf, message=tradability_block)

    buy_block = pnl_buy_block_reason(settings, pf, code=code)
    if buy_block:
        return ApplyResult(applied=False, portfolio=pf, message=buy_block)

    ledger_block = pnl_symbol_ledger_block_reason(settings, code, pf)
    if ledger_block:
        return ApplyResult(applied=False, portfolio=pf, message=ledger_block)

    from agent_reach.daily_run.skill_rejected import trade_blocked_by_rejected

    rejected = trade_blocked_by_rejected(
        "buy",
        code=code,
        name=str(target.get("name", code)),
        settings=settings,
    )
    if rejected:
        return ApplyResult(
            applied=False,
            portfolio=pf,
            message=f"已证伪策略阻断买入：{rejected}",
        )

    price = float(_price_for(target, enriched))
    budget_kwargs: dict[str, Any] = {}
    if cash_limit_bypass:
        budget_kwargs = {
            "deploy_ratio_override": 1.0,
            "max_position_pct_override": 100.0,
        }
    elif max_position_pct_override is not None:
        budget_kwargs["max_position_pct_override"] = float(max_position_pct_override)
    deploy_kwargs = _trade_deploy_budget_kwargs(code, enriched, settings)
    budget_gross = harness_buy_budget(
        total=total,
        deployable=deployable,
        settings=settings,
        **deploy_kwargs,
        **budget_kwargs,
    )
    budget = budget_gross / (1 + commission_rate)
    shares = _round_lot(code, int(budget // price))
    if shares <= 0 and cash_limit_bypass:
        min_lot = _min_lot(code)
        min_cost = min_lot * price * (1 + commission_rate)
        if cash >= min_cost:
            shares = min_lot
    if shares <= 0:
        min_lot = _min_lot(code)
        return ApplyResult(
            applied=False,
            portfolio=pf,
            message=format_min_lot_budget_message(
                code=code,
                price=price,
                buy_budget=budget,
                min_lot=min_lot,
                commission_rate=commission_rate,
            ),
        )

    from agent_reach.daily_run.execution_sim import sim_execution_price, sim_trade_shares

    shares, volume_meta = sim_trade_shares(shares, target, enriched, side="buy", settings=settings)
    price, exec_meta = sim_execution_price(target, enriched, side="buy", settings=settings)
    if shares <= 0 or price is None or price <= 0:
        return ApplyResult(applied=False, portfolio=pf, message=f"{code} 无法买入（股数或价格无效）")

    gross = shares * price
    commission = round(gross * commission_rate, 2)
    total_cost = gross + commission
    if total_cost > cash:
        shares = _round_lot(code, int((cash / (1 + commission_rate)) // price))
        shares, volume_meta = sim_trade_shares(shares, target, enriched, side="buy", settings=settings)
        if shares <= 0:
            return ApplyResult(applied=False, portfolio=pf, message="现金不足")
        gross = shares * price
        commission = round(gross * commission_rate, 2)
        total_cost = gross + commission

    pf["cash"] = round(cash - total_cost, 2)
    pf["trade_session_date"] = _today_str()
    _add_bought_shares(
        holdings,
        code=code,
        name=str(target.get("name", code)),
        shares=shares,
        price=price,
        commission=commission,
    )
    pf["holdings"] = holdings

    if allow_watchlist_changes:
        pf["watchlist"] = [
            w for w in (pf.get("watchlist") or []) if _normalize_code(str(w.get("code", ""))) != code
        ]

    trade = TradeAction(
        side="buy",
        code=code,
        name=str(target.get("name", code)),
        shares=shares,
        price=price,
        amount=round(gross, 2),
        commission=commission,
        reasoning=(
            f"买入 {target.get('name', code)} {shares} 股 @ {price:.2f}（MSS 信号建仓"
            + ("；连续买入建议，临时突破现金限制" if cash_limit_bypass else "")
            + "）"
        ),
        fill_timing=str(exec_meta.get("fill_timing") or ""),
        slippage_rate=exec_meta.get("slippage_rate"),
        volume_limited=bool(volume_meta.get("volume_limited")),
    )
    _recalc_totals(pf, enriched)
    return ApplyResult(applied=True, portfolio=pf, actions=[trade], message=trade.reasoning)


def simulate_buy_analysis(
    pf: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
    *,
    prefer_code: Optional[str] = None,
    cash_limit_bypass: bool = False,
    max_position_pct_override: Optional[float] = None,
) -> dict[str, Any]:
    """Dry-run buy sizing under current harness rules (no portfolio mutation)."""
    from agent_reach.daily_run.harness_policy import _position_policy

    holdings = list(pf.get("holdings") or [])
    prefer = _normalize_code(str(prefer_code or ""))
    position = _position_policy(settings)

    budget_ctx = _buy_budget_context(
        pf,
        enriched,
        settings,
        holdings,
        cash_limit_bypass=cash_limit_bypass,
    )
    if isinstance(budget_ctx, ApplyResult):
        return {
            "allowed": False,
            "buy_shares": 0,
            "block_reason": budget_ctx.message,
            "deploy_ratio": float(position.get("deploy_ratio", 1.0)),
            "max_position_pct": float(position.get("max_position_pct", 35.0)),
        }

    total, cash, deployable, _min_deploy, min_cash_ratio, commission_rate = budget_ctx

    target, resolve_err = _resolve_single_buy_target(prefer, pf, enriched)
    if resolve_err:
        return {
            "allowed": False,
            "buy_shares": 0,
            "block_reason": resolve_err,
            "deploy_ratio": float(position.get("deploy_ratio", 1.0)),
            "max_position_pct": float(position.get("max_position_pct", 35.0)),
        }
    assert target is not None

    code = _normalize_code(str(target["code"]))

    buy_block = pnl_buy_block_reason(settings, pf, code=code)
    if buy_block:
        return {
            "allowed": False,
            "buy_shares": 0,
            "block_reason": buy_block,
            "deploy_ratio": float(position.get("deploy_ratio", 1.0)),
            "max_position_pct": float(position.get("max_position_pct", 35.0)),
        }

    ledger_block = pnl_symbol_ledger_block_reason(settings, code, pf)
    if ledger_block:
        return {
            "allowed": False,
            "buy_shares": 0,
            "block_reason": ledger_block,
            "deploy_ratio": float(position.get("deploy_ratio", 1.0)),
            "max_position_pct": float(position.get("max_position_pct", 35.0)),
        }

    from agent_reach.daily_run.skill_rejected import trade_blocked_by_rejected

    rejected = trade_blocked_by_rejected(
        "buy",
        code=code,
        name=str(target.get("name", code)),
        settings=settings,
    )
    if rejected:
        return {
            "allowed": False,
            "buy_shares": 0,
            "block_reason": f"已证伪策略阻断买入：{rejected}",
            "deploy_ratio": float(position.get("deploy_ratio", 1.0)),
            "max_position_pct": float(position.get("max_position_pct", 35.0)),
        }

    price = float(_price_for(target, enriched))
    budget_kwargs: dict[str, Any] = {}
    if cash_limit_bypass:
        budget_kwargs = {
            "deploy_ratio_override": 1.0,
            "max_position_pct_override": 100.0,
        }
    elif max_position_pct_override is not None:
        budget_kwargs["max_position_pct_override"] = float(max_position_pct_override)
    deploy_kwargs = _trade_deploy_budget_kwargs(code, enriched, settings)
    budget_gross = harness_buy_budget(
        total=total,
        deployable=deployable,
        settings=settings,
        **deploy_kwargs,
        **budget_kwargs,
    )
    budget = budget_gross / (1 + commission_rate)
    shares = _round_lot(code, int(budget // price))
    if shares <= 0 and cash_limit_bypass:
        min_lot = _min_lot(code)
        min_cost = min_lot * price * (1 + commission_rate)
        if cash >= min_cost:
            shares = min_lot
    if shares <= 0:
        min_lot = _min_lot(code)
        return {
            "allowed": False,
            "buy_shares": 0,
            "block_reason": format_min_lot_budget_message(
                code=code,
                price=price,
                buy_budget=budget,
                min_lot=min_lot,
                commission_rate=commission_rate,
            ),
            "code": code,
            "name": str(target.get("name", code)),
            "price": price,
            "buy_budget": budget,
            "min_lot_cost": min_lot * price * (1 + commission_rate),
            "deployable": deployable,
            "cash": cash,
            "total": total,
            "min_cash_ratio": min_cash_ratio,
            "deploy_ratio": float(position.get("deploy_ratio", 1.0)),
            "max_position_pct": float(position.get("max_position_pct", 35.0)),
        }

    gross = shares * price
    commission = round(gross * commission_rate, 2)
    total_cost = gross + commission
    if total_cost > cash:
        shares = _round_lot(code, int((cash / (1 + commission_rate)) // price))
        if shares <= 0:
            return {
                "allowed": False,
                "buy_shares": 0,
                "block_reason": "现金不足",
                "deploy_ratio": float(position.get("deploy_ratio", 1.0)),
                "max_position_pct": float(position.get("max_position_pct", 35.0)),
            }

    return {
        "allowed": True,
        "buy_shares": shares,
        "block_reason": None,
        "code": code,
        "name": str(target.get("name", code)),
        "price": price,
        "deploy_ratio": float(position.get("deploy_ratio", 1.0)),
        "max_position_pct": float(position.get("max_position_pct", 35.0)),
    }


def format_min_lot_budget_message(
    *,
    code: str,
    price: float,
    buy_budget: float,
    min_lot: int,
    min_lot_cost: Optional[float] = None,
    commission_rate: float = 0.0015,
) -> str:
    lot_cost = (
        float(min_lot_cost)
        if min_lot_cost is not None
        else min_lot * price * (1 + commission_rate)
    )
    return (
        f"{code} 可部署买入预算 ¥{buy_budget:,.0f} 不足一手"
        f"（{min_lot} 股 @ ¥{price:.2f} ≈ ¥{lot_cost:,.0f}）"
    )


def buy_budget_footer_markdown(
    pf: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
    *,
    prefer_code: str,
) -> Optional[str]:
    """One-line deploy budget context for Feishu cards when buy is budget-blocked."""
    analysis = simulate_buy_analysis(pf, enriched, settings, prefer_code=prefer_code)
    block = str(analysis.get("block_reason") or "")
    if analysis.get("allowed") or "可部署买入预算" not in block:
        return None

    parts: list[str] = []
    deployable = analysis.get("deployable")
    min_cash_ratio = analysis.get("min_cash_ratio")
    if deployable is not None and min_cash_ratio is not None:
        parts.append(
            f"可部署现金 ¥{float(deployable):,.0f}（min_cash {float(min_cash_ratio):.0%} 保留）"
        )
    deploy_ratio = analysis.get("deploy_ratio")
    buy_budget = analysis.get("buy_budget")
    if deploy_ratio is not None and buy_budget is not None:
        parts.append(
            f"deploy_ratio {float(deploy_ratio):.0%} → 本笔预算 ¥{float(buy_budget):,.0f}"
        )
    min_lot_cost = analysis.get("min_lot_cost")
    if min_lot_cost is not None:
        parts.append(f"一手约 ¥{float(min_lot_cost):,.0f}")
    if not parts:
        return None
    return "💰 **部署预算：** " + " · ".join(parts)


def trade_buy_budget_blocked(record: dict[str, Any]) -> bool:
    """Decision- or trade-record-level deploy budget precheck block."""
    if record.get("block_kind") == "buy_budget":
        return True
    reasoning = str(record.get("reasoning") or "")
    return "可部署买入预算" in reasoning


def _symbol_is_holding(code: str, pf: dict[str, Any]) -> bool:
    norm = _normalize_code(code)
    for h in pf.get("holdings") or []:
        if _normalize_code(str(h.get("code") or "")) == norm:
            return True
    return False


def _annotate_buy_budget_reason(
    reason: str,
    *,
    code: str,
    pf: dict[str, Any],
    settings: dict[str, Any],
) -> str:
    if _symbol_is_holding(code, pf):
        return reason
    from agent_reach.daily_run.deploy_signal_policy import deploy_signal_cfg

    cfg = deploy_signal_cfg(settings)
    if not cfg.get("watchlist_buy_precheck_only", True):
        return reason
    label = str(cfg.get("card_label_watchlist_budget") or "观察池买入预算不足")
    if label in reason:
        return reason
    return f"【{label}】{reason}"


def buy_budget_precheck_reason(
    pf: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
    *,
    prefer_code: str,
    cash_limit_bypass: bool = False,
    max_position_pct_override: Optional[float] = None,
) -> Optional[str]:
    """Return a block reason when the decision symbol cannot afford one lot."""
    analysis = simulate_buy_analysis(
        pf,
        enriched,
        settings,
        prefer_code=prefer_code,
        cash_limit_bypass=cash_limit_bypass,
        max_position_pct_override=max_position_pct_override,
    )
    if analysis.get("allowed"):
        return None
    reason = str(analysis.get("block_reason") or "").strip()
    reason = reason or "买入预算不足"
    return _annotate_buy_budget_reason(
        reason,
        code=prefer_code,
        pf=pf,
        settings=settings,
    )


def watchlist_affordability_markdown(
    pf: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
    watchlist: list[dict[str, Any]],
) -> list[str]:
    """Flag watchlist names whose min lot exceeds the current per-trade deploy budget."""
    if not watchlist:
        return []

    from agent_reach.daily_run.harness_policy import _position_policy

    holdings = list(pf.get("holdings") or [])
    budget_ctx = _buy_budget_context(pf, enriched, settings, holdings)
    if isinstance(budget_ctx, ApplyResult):
        return []

    total, _cash, deployable, _min_deploy, min_cash_ratio, commission_rate = budget_ctx
    position = _position_policy(settings)
    deploy_ratio = float(position.get("deploy_ratio", 1.0))
    budget_gross = harness_buy_budget(total=total, deployable=deployable, settings=settings)
    per_budget = budget_gross / (1 + commission_rate)

    unaffordable: list[str] = []
    for row in watchlist:
        code = _normalize_code(str(row.get("code", "")))
        if not code:
            continue
        target = _resolve_buy_row(code, pf, enriched)
        if target is None:
            continue
        price = _price_for(target, enriched)
        if price is None or price <= 0:
            continue
        min_lot = _min_lot(code)
        min_cost = min_lot * float(price) * (1 + commission_rate)
        if min_cost <= per_budget + 0.01:
            continue
        name = str(target.get("name") or code)
        unaffordable.append(
            f"**{name}** ({code}) 一手约 ¥{min_cost:,.0f} > 单笔预算 ¥{per_budget:,.0f}"
        )

    if not unaffordable:
        return []

    lines = [
        (
            f"- ⚠️ **预算不可达观察标的**"
            f"（min_cash {min_cash_ratio:.0%} · deploy {deploy_ratio:.0%} · 单笔约 ¥{per_budget:,.0f}）："
        )
    ]
    lines.extend(f"  · {item}" for item in unaffordable[:5])
    return lines


def portfolio_deploy_budget_markdown(
    pf: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
) -> Optional[str]:
    """Portfolio-level deploy budget snapshot for close review cards."""
    from agent_reach.daily_run.harness_policy import _position_policy

    holdings = list(pf.get("holdings") or [])
    budget_ctx = _buy_budget_context(pf, enriched, settings, holdings)
    position = _position_policy(settings)
    deploy_ratio = float(position.get("deploy_ratio", 1.0))
    if isinstance(budget_ctx, ApplyResult):
        return (
            f"- **部署预算：** {budget_ctx.message}"
            f" · deploy_ratio {deploy_ratio:.0%}"
        )

    total, _cash, deployable, _min_deploy, min_cash_ratio, commission_rate = budget_ctx
    budget_gross = harness_buy_budget(total=total, deployable=deployable, settings=settings)
    budget = budget_gross / (1 + commission_rate)
    return (
        f"- **部署预算：** 可部署 ¥{deployable:,.0f}（min_cash {min_cash_ratio:.0%} 保留）"
        f" · deploy_ratio {deploy_ratio:.0%} → 单笔约 ¥{budget:,.0f}"
    )


def _holdings_market_value(
    holdings: list[dict[str, Any]],
    enriched: dict[str, dict[str, Any]],
) -> float:
    total_mv = 0.0
    for h in holdings:
        code = _normalize_code(str(h.get("code", "")))
        row = {**h, **enriched.get(code, {})}
        price = _price_for(row, enriched) or h.get("cost") or 0
        total_mv += int(h.get("shares") or 0) * float(price)
    return round(total_mv, 2)


def _ledger_expected_cash_today() -> Optional[float]:
    """Best-effort end-of-day cash from morning baseline + today's ledger."""
    try:
        from agent_reach.daily_run.capital_events import net_capital_flow
        from agent_reach.daily_run.close_portfolio_summary import expected_end_cash_from_ledger
        from agent_reach.daily_run.trade_calendar import today_shanghai
        from agent_reach.daily_run.weekly_report import _load_trade_ledger_range
        from agent_reach.daily_run.workflows import load_morning_baseline

        morning_bl = load_morning_baseline()
        morning_cash = float((morning_bl.get("portfolio") or {}).get("cash") or 0)
        day = today_shanghai()
        ledger = _load_trade_ledger_range(day, day)
        return expected_end_cash_from_ledger(
            morning_cash,
            ledger,
            capital_flow=net_capital_flow(day),
        )
    except Exception:
        return None


def _buy_budget_context(
    pf: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
    holdings: list[dict[str, Any]],
    *,
    cash_limit_bypass: bool = False,
) -> tuple[float, float, float, float, float, float] | ApplyResult:
    thresholds = settings.get("thresholds", {})
    min_cash_ratio = float(thresholds.get("min_cash_ratio", min_cash_ratio_default(settings)))
    cash = float(pf.get("cash") or 0)
    mv = _holdings_market_value(holdings, enriched)
    total = float(pf.get("total") or 0)
    recomputed = round(cash + mv, 2)
    if total <= 0 or abs(total - recomputed) > 1.0:
        total = recomputed

    if cash < 0:
        ledger_cash = _ledger_expected_cash_today()
        if ledger_cash is not None and ledger_cash > cash:
            cash = ledger_cash
            total = round(cash + mv, 2)

    if cash_limit_bypass:
        min_cash = 0.0
    else:
        nav_for_reserve = max(0.0, total, mv)
        min_cash = nav_for_reserve * min_cash_ratio
    deployable = max(0.0, cash - min_cash)
    min_deploy = min_deploy_cash_default(settings)

    if cash < 0:
        return ApplyResult(
            applied=False,
            portfolio=pf,
            message=f"账户现金为负（¥{cash:,.0f}），暂不可加仓（请核对 portfolio/ledger）",
        )
    if deployable < min_deploy:
        return ApplyResult(
            applied=False,
            portfolio=pf,
            message=f"可部署现金 ¥{deployable:,.0f} 不足（最低部署 ¥{min_deploy:,.0f}）",
        )

    commission_rate = friction_commission_rate_default(settings)
    return total, cash, deployable, min_deploy, min_cash_ratio, commission_rate


def _resolve_buy_row(
    code: str,
    pf: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
) -> Optional[dict[str, Any]]:
    code = _normalize_code(code)
    if not code:
        return None

    row: dict[str, Any] = {}
    for h in pf.get("holdings") or []:
        if _normalize_code(str(h.get("code", ""))) == code:
            row = dict(h)
            break
    for w in pf.get("watchlist") or []:
        if _normalize_code(str(w.get("code", ""))) == code:
            row = {**row, **dict(w)}
            break
    row = {**row, **enriched.get(code, {})}
    row["code"] = code
    if not row.get("name"):
        row["name"] = enriched.get(code, {}).get("name", code)
    if _price_for(row, enriched) is None:
        return None
    return row


def _resolve_single_buy_target(
    prefer_code: Optional[str],
    pf: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Resolve one buy target from the decision symbol only (no watchlist ranking)."""
    prefer = _normalize_code(str(prefer_code or ""))
    if not prefer:
        return None, "买入决策缺少标的代码"
    row = _resolve_buy_row(prefer, pf, enriched)
    if row is None:
        return None, f"{prefer} 不在持仓/观察池或缺少报价"
    return row, None


def _min_lot(code: str) -> int:
    text = str(code).zfill(6)
    return 200 if text.startswith("688") else 100


def _add_bought_shares(
    holdings: list[dict[str, Any]],
    *,
    code: str,
    name: str,
    shares: int,
    price: float,
    commission: float = 0.0,
) -> None:
    """Add shares; merge weighted average cost (incl. commission) and mark T+1 lock."""
    code = _normalize_code(code)
    buy_cost = shares * price + float(commission or 0)
    for row in holdings:
        if _normalize_code(str(row.get("code", ""))) == code:
            old_shares = int(row.get("shares") or 0)
            old_cost = float(row.get("cost") or price)
            new_shares = old_shares + shares
            old_basis = old_shares * old_cost
            row["shares"] = new_shares
            row["cost"] = round((old_basis + buy_cost) / new_shares, 4)
            row["today_buy_shares"] = holding_today_buy_shares(row) + shares
            return

    per_share = buy_cost / shares if shares > 0 else price
    holdings.append(
        {
            "code": code,
            "name": name,
            "shares": shares,
            "cost": round(per_share, 4),
            "today_buy_shares": shares,
            "days_held": 0,
            "acquired_date": trade_calendar.today_shanghai().isoformat(),
        }
    )


def _recalc_totals(pf: dict[str, Any], enriched: dict[str, dict[str, Any]]) -> None:
    cash = float(pf.get("cash") or 0)
    mv = 0.0
    for h in pf.get("holdings") or []:
        code = _normalize_code(str(h.get("code", "")))
        # Merge enriched (freshest quote) over the holding's own possibly-stale
        # embedded `price` first — same idiom as `_holding_unrealized_pnl` —
        # so `total`/`cash_ratio` mark to the same price used elsewhere for
        # per-holding P&L (e.g. weekly_report._holding_pnl_rows), instead of a
        # snapshot price captured earlier in the same run.
        row = {**h, **enriched.get(code, {})}
        price = _price_for(row, enriched) or h.get("cost") or 0
        mv += int(h.get("shares") or 0) * float(price)
    total = round(cash + mv, 2)
    pf["total"] = total
    pf["cash_ratio"] = round(cash / total, 4) if total > 0 else 1.0


def _enriched_symbols(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return build_enriched_symbols(snapshot)


def _price_for(row: dict[str, Any], enriched: dict[str, dict[str, Any]]) -> Optional[float]:
    code = _normalize_code(str(row.get("code", "")))
    for src in (row, enriched.get(code, {})):
        p = src.get("price")
        if p is not None:
            return float(p)
        p = src.get("cost")
        if p is not None:
            return float(p)
    return None


def _symbol_score(row: dict[str, Any], decision: Any, settings: dict[str, Any]) -> float:
    """Rank symbols: higher = better buy candidate."""
    from agent_reach.daily_run.harness_policy import harness_symbol_score

    return harness_symbol_score(row, settings, decision=decision)


def _round_lot(code: str, shares: int, *, total_shares: Optional[int] = None) -> int:
    """Round to board lot size (STAR 688 = 200, else 100).

    When ``total_shares`` (the full remaining position) is given, this is a
    sell-sizing call: a partial-sell amount below one lot must round UP to one
    lot rather than be dropped to 0 (the board lot is a minimum order size, not
    a rounding-down unit) — as long as the position actually holds ≥1 lot.
    Selling the entire remaining position is always allowed regardless of lot
    size.
    """
    if shares <= 0:
        return 0
    lot = 200 if str(code).zfill(6).startswith("688") else 100
    if total_shares is not None and shares >= total_shares:
        return total_shares
    if shares >= lot:
        return (shares // lot) * lot
    if total_shares is not None:
        return lot if total_shares >= lot else total_shares
    return 0


def _decision_reason(decision: Any, fallback: str) -> str:
    reason = getattr(decision, "reasoning", None) if not isinstance(decision, dict) else decision.get("reasoning")
    return reason or fallback


def _decision_block_kind(decision: Any) -> Optional[str]:
    if decision is None:
        return None
    if isinstance(decision, dict):
        return decision.get("block_kind")
    return getattr(decision, "block_kind", None)


def render_apply_markdown(result: ApplyResult, *, decision: Optional[Any] = None) -> str:
    if not result.applied:
        if _decision_block_kind(decision) == "buy_budget":
            reasoning = ""
            if isinstance(decision, dict):
                reasoning = str(decision.get("reasoning") or "")
            elif decision is not None:
                reasoning = str(getattr(decision, "reasoning", "") or "")
            if "观察池" in reasoning:
                return "**观察池：** 买入预算预检阻断（部署预算不足一手，非现金不足）"
            return "**调仓执行：** 决策层预算预检阻断，未进入 paper 落账"
        return f"**调仓执行：** 未执行 — {result.message}"
    lines = ["**调仓执行（paper）：**"]
    payloads = result.action_payloads or [a.to_dict() for a in result.actions]
    for a in payloads:
        side = "买入" if a.get("side") == "buy" else "卖出"
        lines.append(
            f"- {side} **{a.get('name')}** ({a.get('code')}) {a.get('shares')} 股 @ {float(a['price']):.2f} "
            f"≈ ¥{float(a['amount']):,.0f}（佣金 ¥{float(a['commission']):.2f}）"
        )
        if a.get("side") == "sell" and a.get("realized_pnl") is not None:
            pnl = float(a["realized_pnl"])
            pct = a.get("realized_pnl_pct")
            pct_s = f"（{float(pct):+.2f}%）" if pct is not None else ""
            lines.append(f"  · 已实现盈亏 **{pnl:+,.0f}**{pct_s}")
    lines.append(f"\n{result.message}")
    return "\n".join(lines)

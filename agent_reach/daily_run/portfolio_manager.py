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

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "code": self.code,
            "name": self.name,
            "shares": self.shares,
            "price": self.price,
            "amount": self.amount,
            "commission": self.commission,
            "reasoning": self.reasoning,
        }


@dataclass
class ApplyResult:
    applied: bool
    portfolio: dict[str, Any]
    actions: list[TradeAction] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "message": self.message,
            "actions": [a.to_dict() for a in self.actions],
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


def load_daily_trade_state() -> dict[str, Any]:
    path = daily_trade_state_path()
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


def global_trades_today() -> int:
    return len(load_daily_trade_state().get("fingerprints") or [])


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
) -> None:
    if not actions:
        return
    p = path or default_ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    at = datetime.now(timezone.utc).isoformat()
    raw_actions = [a.to_dict() for a in actions]
    from agent_reach.daily_run.realized_pnl import enrich_sell_actions, load_ledger_entries

    prior = load_ledger_entries(path=p, end=trade_calendar.today_shanghai())
    enriched = enrich_sell_actions(
        prior,
        raw_actions,
        entry_at=at,
        trade_id=trade_id,
    )
    entry = {
        "at": at,
        "trade_id": trade_id,
        "decision_action": decision_action,
        "actions": enriched,
    }
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


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
) -> int:
    """Shares to sell using harness-evolved sell_ratio (deep vs non-deep)."""
    if total_shares <= 0:
        return 0
    ratio_key = "sell_ratio" if is_deep_loss else "non_deep_loss_sell_ratio"
    ratio = deep_loss_policy_default(settings, ratio_key)
    if ratio >= 0.999:
        return total_shares
    sold = _round_lot(code, int(total_shares * ratio))
    if sold <= 0:
        return 0
    return min(sold, total_shares)


def deep_loss_sell_analysis(
    pf: dict[str, Any],
    holding: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Harness deep-loss sell gate: thresholds, cover requirement, sell ratio."""
    policy = deep_loss_policy(settings)
    unrealized, pct = _holding_unrealized_pnl(holding, enriched)
    deep = is_deep_loss_holding(holding, enriched, settings)
    loss_abs = abs(unrealized) if unrealized < -0.01 else 0.0
    cover_ratio = float(policy.get("cover_ratio", 1.0))
    coverable = portfolio_coverable_gains(
        pf,
        enriched,
        settings,
        exclude_code=str(holding.get("code") or ""),
    )
    required_cover = round(loss_abs * cover_ratio, 2) if deep and cover_ratio > 0 else 0.0
    code = _normalize_code(str(holding.get("code") or ""))
    total_shares = int(holding.get("shares") or 0)
    sell_shares = resolve_deep_loss_sell_shares(
        total_shares,
        code,
        settings,
        is_deep_loss=deep,
    )
    ratio_key = "sell_ratio" if deep else "non_deep_loss_sell_ratio"
    effective_sell_ratio = float(policy.get(ratio_key, deep_loss_policy_default(settings, ratio_key)))
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
) -> Optional[str]:
    """Return block message when harness deep-loss sell conditions fail."""
    return deep_loss_sell_analysis(pf, holding, enriched, settings).get("block_reason")


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


def sync_portfolio_holding_days(
    portfolio: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Refresh days_held from acquired_date for all holdings."""
    pf = dict(portfolio)
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
) -> ApplyResult:
    """Apply paper buy/sell to portfolio.json based on intraday TradeDecision.

    Watchlist membership is NOT changed here by default — only morning/close
    via watchlist_manager.adjust_watchlist().
    """
    if not is_auto_adjust_enabled(settings):
        return ApplyResult(applied=False, portfolio=portfolio, message="auto_adjust 未启用")

    settings = effective_settings(settings)

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
        return ApplyResult(applied=False, portfolio=portfolio, message="买入信号被风控或摩擦成本阻断")

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
        return _apply_buy(
            pf,
            enriched,
            settings,
            allow_watchlist_changes=allow_watchlist_changes,
            prefer_code=prefer_code or None,
        )

    return ApplyResult(applied=False, portfolio=portfolio, message=f"未知决策 {action}")


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

    if not holding_is_sellable(target, settings):
        return ApplyResult(applied=False, portfolio=pf, message=f"{code} 在 {lock_days} 天锁定期内，无法卖出")

    ledger_block = pnl_symbol_ledger_block_reason(settings, code, pf)
    if ledger_block:
        return ApplyResult(applied=False, portfolio=pf, message=ledger_block)

    target.update(enriched.get(code, {}))
    sell_analysis = deep_loss_sell_analysis(pf, target, enriched, settings)
    if not sell_analysis["allowed"]:
        return ApplyResult(applied=False, portfolio=pf, message=str(sell_analysis["block_reason"]))

    shares = int(sell_analysis["sell_shares"] or 0)
    price = _price_for(target, enriched)
    if shares <= 0 or price is None or price <= 0:
        return ApplyResult(applied=False, portfolio=pf, message=f"{code} 无法卖出（股数或价格无效）")

    commission_rate = friction_commission_rate_default(settings)
    gross = shares * price
    commission = round(gross * commission_rate, 2)
    proceeds = gross - commission

    total_shares = int(target.get("shares") or 0)
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
    if sell_ratio < 0.999:
        label = "深度套牢分批" if sell_analysis.get("is_deep_loss") else "非深亏分批"
        sell_note = f"（{label} sell_ratio={sell_ratio:.0%}）"
    trade = TradeAction(
        side="sell",
        code=code,
        name=str(target.get("name", code)),
        shares=shares,
        price=price,
        amount=round(gross, 2),
        commission=commission,
        reasoning=_decision_reason(decision, f"卖出 {target.get('name', code)} {shares} 股{sell_note}"),
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
) -> ApplyResult:
    holdings = list(pf.get("holdings") or [])
    held_codes = {_normalize_code(str(h.get("code", ""))) for h in holdings}
    prefer = _normalize_code(str(prefer_code or ""))

    budget_ctx = _buy_budget_context(pf, enriched, settings, holdings)
    if isinstance(budget_ctx, ApplyResult):
        return budget_ctx
    total, cash, deployable, min_deploy, min_cash_ratio, commission_rate = budget_ctx

    buy_block = pnl_buy_block_reason(settings, pf)
    if buy_block:
        return ApplyResult(applied=False, portfolio=pf, message=buy_block)

    target: Optional[dict[str, Any]] = None
    if prefer:
        prefer_row = _resolve_buy_row(prefer, pf, enriched)
        if prefer_row is not None:
            prefer_price = float(_price_for(prefer_row, enriched))
            if _can_afford_min_lot(
                prefer,
                prefer_price,
                deployable=deployable,
                commission_rate=commission_rate,
                min_deploy=min_deploy,
                total=total,
                settings=settings,
            ):
                target = prefer_row

    if target is None:
        candidates = _watchlist_buy_candidates(pf, enriched, held_codes)
        if not candidates:
            max_t = max_total_symbols(settings)
            if unique_symbol_count(pf) >= max_t:
                return ApplyResult(
                    applied=False,
                    portfolio=pf,
                    message=f"持仓+观察池已达合计上限 {max_t} 只，且无观察池可买标的",
                )
            if prefer:
                return ApplyResult(
                    applied=False,
                    portfolio=pf,
                    message=f"决策标的 {prefer} 资金不足一手，且观察池无可买入标的（或缺少报价）",
                )
            return ApplyResult(applied=False, portfolio=pf, message="观察池无可买入标的（或缺少报价）")

        candidates.sort(key=lambda x: _symbol_score(x, None, settings), reverse=True)
        target = candidates[0]

    code = _normalize_code(str(target["code"]))

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
    budget_gross = harness_buy_budget(total=total, deployable=deployable, settings=settings)
    budget = budget_gross / (1 + commission_rate)
    shares = _round_lot(code, int(budget // price))
    if shares <= 0:
        return ApplyResult(applied=False, portfolio=pf, message=f"现金不足以买入 {code} 最小单位")

    gross = shares * price
    commission = round(gross * commission_rate, 2)
    total_cost = gross + commission
    if total_cost > cash:
        shares = _round_lot(code, int((cash / (1 + commission_rate)) // price))
        if shares <= 0:
            return ApplyResult(applied=False, portfolio=pf, message="现金不足")
        gross = shares * price
        commission = round(gross * commission_rate, 2)
        total_cost = gross + commission

    pf["cash"] = round(cash - total_cost, 2)
    _add_bought_shares(
        holdings,
        code=code,
        name=str(target.get("name", code)),
        shares=shares,
        price=price,
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
        reasoning=f"买入 {target.get('name', code)} {shares} 股 @ {price:.2f}（MSS 信号建仓）",
    )
    _recalc_totals(pf, enriched)
    return ApplyResult(applied=True, portfolio=pf, actions=[trade], message=trade.reasoning)


def _buy_budget_context(
    pf: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
    holdings: list[dict[str, Any]],
) -> tuple[float, float, float, float, float, float] | ApplyResult:
    thresholds = settings.get("thresholds", {})
    min_cash_ratio = float(thresholds.get("min_cash_ratio", min_cash_ratio_default(settings)))
    total = float(pf.get("total") or 0)
    cash = float(pf.get("cash") or 0)
    if total <= 0:
        total = cash + sum(
            int(h.get("shares") or 0)
            * float(enriched.get(_normalize_code(str(h.get("code", ""))), {}).get("price") or h.get("cost") or 0)
            for h in holdings
        )

    min_cash = total * min_cash_ratio
    deployable = cash - min_cash
    min_deploy = min_deploy_cash_default(settings)
    if deployable < min_deploy:
        return ApplyResult(
            applied=False,
            portfolio=pf,
            message=f"可部署现金 {deployable:.0f} 不足（最低部署 {min_deploy:.0f}）",
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


def _watchlist_buy_candidates(
    pf: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    held_codes: set[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for w in pf.get("watchlist") or []:
        code = _normalize_code(str(w.get("code", "")))
        if code in held_codes:
            continue
        row = dict(w)
        row.update(enriched.get(code, {}))
        if _price_for(row, enriched) is None:
            continue
        candidates.append(row)
    return candidates


def _min_lot(code: str) -> int:
    text = str(code).zfill(6)
    return 200 if text.startswith("688") else 100


def _can_afford_min_lot(
    code: str,
    price: float,
    *,
    deployable: float,
    commission_rate: float,
    min_deploy: float,
    total: float,
    settings: dict[str, Any],
) -> bool:
    if price <= 0 or deployable < min_deploy:
        return False
    budget_gross = harness_buy_budget(total=total, deployable=deployable, settings=settings)
    budget = budget_gross / (1 + commission_rate)
    shares = _round_lot(code, int(budget // price))
    return shares >= _min_lot(code)


def _add_bought_shares(
    holdings: list[dict[str, Any]],
    *,
    code: str,
    name: str,
    shares: int,
    price: float,
) -> None:
    code = _normalize_code(code)
    for row in holdings:
        if _normalize_code(str(row.get("code", ""))) == code:
            old_shares = int(row.get("shares") or 0)
            old_cost = float(row.get("cost") or price)
            new_shares = old_shares + shares
            row["shares"] = new_shares
            row["cost"] = round((old_shares * old_cost + shares * price) / new_shares, 4)
            return

    holdings.append(
        {
            "code": code,
            "name": name,
            "shares": shares,
            "cost": round(price, 4),
            "days_held": 0,
            "acquired_date": trade_calendar.today_shanghai().isoformat(),
        }
    )


def _recalc_totals(pf: dict[str, Any], enriched: dict[str, dict[str, Any]]) -> None:
    cash = float(pf.get("cash") or 0)
    mv = 0.0
    for h in pf.get("holdings") or []:
        code = _normalize_code(str(h.get("code", "")))
        price = _price_for(h, enriched) or h.get("cost") or 0
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


def _round_lot(code: str, shares: int) -> int:
    if shares <= 0:
        return 0
    text = str(code).zfill(6)
    if text.startswith("688"):
        lot = 200
        return (shares // lot) * lot if shares >= lot else 0
    lot = 100
    return (shares // lot) * lot


def _decision_reason(decision: Any, fallback: str) -> str:
    reason = getattr(decision, "reasoning", None) if not isinstance(decision, dict) else decision.get("reasoning")
    return reason or fallback


def render_apply_markdown(result: ApplyResult) -> str:
    if not result.applied:
        return f"**调仓执行：** 未执行 — {result.message}"
    lines = ["**调仓执行（paper）：**"]
    for a in result.actions:
        side = "买入" if a.side == "buy" else "卖出"
        lines.append(
            f"- {side} **{a.name}** ({a.code}) {a.shares} 股 @ {a.price:.2f} "
            f"≈ ¥{a.amount:,.0f}（佣金 ¥{a.commission:.2f}）"
        )
    lines.append(f"\n{result.message}")
    return "\n".join(lines)

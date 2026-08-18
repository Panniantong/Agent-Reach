# -*- coding: utf-8
"""Paper portfolio auto-adjust based on MSS trade signals."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run import trade_calendar
from agent_reach.daily_run.harness_policy import min_cash_ratio_default, runtime_int_default, runtime_float_default
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
        return _apply_sell(pf, enriched, settings, decision, allow_watchlist_changes=allow_watchlist_changes)
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
) -> ApplyResult:
    holdings = list(pf.get("holdings") or [])
    if not holdings:
        return ApplyResult(applied=False, portfolio=pf, message="无持仓可卖")

    lock_days = runtime_int_default(settings, "trading", "holding_lock_days")
    sellable = []
    for h in holdings:
        code = _normalize_code(str(h.get("code", "")))
        if not holding_is_sellable(h, settings):
            continue
        row = dict(h)
        row.update(enriched.get(code, {}))
        sellable.append(row)

    if not sellable:
        return ApplyResult(applied=False, portfolio=pf, message=f"持仓均在 {lock_days} 天锁定期内")

    # Sell weakest position first (lowest change_pct, then lowest score)
    sellable.sort(key=lambda x: (_symbol_score(x, decision, settings), x.get("change_pct") or 0))

    target = sellable[0]
    code = _normalize_code(str(target["code"]))
    shares = int(target.get("shares") or 0)
    price = _price_for(target, enriched)
    if shares <= 0 or price is None or price <= 0:
        return ApplyResult(applied=False, portfolio=pf, message=f"{code} 无法卖出（股数或价格无效）")

    commission_rate = float(settings.get("trading", {}).get("commission_rate", 0.0015))
    gross = shares * price
    commission = round(gross * commission_rate, 2)
    proceeds = gross - commission

    pf["holdings"] = [h for h in holdings if _normalize_code(str(h.get("code", ""))) != code]
    pf["cash"] = round(float(pf.get("cash") or 0) + proceeds, 2)

    if allow_watchlist_changes and portfolio_settings(settings).get("add_sold_to_watchlist", True):
        watchlist = list(pf.get("watchlist") or [])
        codes = {_normalize_code(str(w.get("code", ""))) for w in watchlist}
        if code not in codes and unique_symbol_count(pf) < max_total_symbols(settings):
            watchlist.append({"code": code, "name": target.get("name", code)})
            pf["watchlist"] = watchlist

    trade = TradeAction(
        side="sell",
        code=code,
        name=str(target.get("name", code)),
        shares=shares,
        price=price,
        amount=round(gross, 2),
        commission=commission,
        reasoning=_decision_reason(decision, f"卖出 {target.get('name', code)} {shares} 股"),
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
    candidates = []
    for w in pf.get("watchlist") or []:
        code = _normalize_code(str(w.get("code", "")))
        if code in held_codes:
            continue
        row = dict(w)
        row.update(enriched.get(code, {}))
        price = _price_for(row, enriched)
        if price is None or price <= 0:
            continue
        candidates.append(row)

    if not candidates:
        max_t = max_total_symbols(settings)
        if unique_symbol_count(pf) >= max_t:
            return ApplyResult(
                applied=False,
                portfolio=pf,
                message=f"持仓+观察池已达合计上限 {max_t} 只，且无观察池可买标的",
            )
        return ApplyResult(applied=False, portfolio=pf, message="观察池无可买入标的（或缺少报价）")

    candidates.sort(key=lambda x: _symbol_score(x, None, settings), reverse=True)
    prefer = _normalize_code(str(prefer_code or ""))
    if prefer:
        preferred = [c for c in candidates if _normalize_code(str(c.get("code", ""))) == prefer]
        target = preferred[0] if preferred else candidates[0]
    else:
        target = candidates[0]
    code = _normalize_code(str(target["code"]))

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

    thresholds = settings.get("thresholds", {})
    min_cash_ratio = float(thresholds.get("min_cash_ratio", min_cash_ratio_default(settings)))
    total = float(pf.get("total") or 0)
    cash = float(pf.get("cash") or 0)
    if total <= 0:
        total = cash + sum(
            int(h.get("shares") or 0) * float(enriched.get(_normalize_code(str(h.get("code", ""))), {}).get("price") or h.get("cost") or 0)
            for h in holdings
        )

    min_cash = total * min_cash_ratio
    deployable = cash - min_cash
    min_deploy = float(portfolio_settings(settings).get("min_deploy_cash", 1000))
    if deployable < min_deploy:
        return ApplyResult(
            applied=False,
            portfolio=pf,
            message=f"可部署现金 {deployable:.0f} 不足（需保留 {min_cash_ratio:.0%} 现金）",
        )

    commission_rate = float(settings.get("trading", {}).get("commission_rate", 0.0015))
    # No per-position cap — use all deployable cash minus commission headroom
    budget = deployable / (1 + commission_rate)
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
    holdings.append(
        {
            "code": code,
            "name": target.get("name", code),
            "shares": shares,
            "cost": round(price, 4),
            "days_held": 0,
            "acquired_date": trade_calendar.today_shanghai().isoformat(),
        }
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
    """Rank symbols: higher = better buy candidate / lower sell priority."""
    base = 50.0
    if decision is not None:
        lb = getattr(decision, "lookback_mss", None)
        if lb is None and isinstance(decision, dict):
            lb = decision.get("lookback_mss")
        if lb is not None:
            base = float(lb)
    chg = row.get("change_pct")
    if chg is not None:
        base += float(chg) * 0.5
    pos = row.get("position_20d")
    if pos is not None:
        base += (0.5 - float(pos)) * 10
    from agent_reach.daily_run.harness_policy import kronos_score_adjustment

    code = _normalize_code(str(row.get("code", "")))
    base += kronos_score_adjustment(code, settings)
    return base


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

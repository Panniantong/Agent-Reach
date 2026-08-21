# -*- coding: utf-8
"""FIFO realized P&L from trade ledger + portfolio overview."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from agent_reach.daily_run.portfolio_manager import (
    dedupe_trade_ledger_entries,
    default_ledger_path,
)
from agent_reach.daily_run.snapshot_builder import _normalize_code
from agent_reach.daily_run.trade_calendar import today_shanghai


@dataclass
class RealizedSellRow:
    date: str
    code: str
    name: str
    shares: int
    price: float
    amount: float
    commission: float
    cost_basis: float
    realized_pnl: float
    realized_pnl_pct: Optional[float] = None
    trade_id: Optional[str] = None
    reasoning: str = ""
    at: str = ""
    avg_buy_price: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "at": self.at,
            "code": self.code,
            "name": self.name,
            "shares": self.shares,
            "price": self.price,
            "sell_price": self.price,
            "avg_buy_price": self.avg_buy_price,
            "amount": self.amount,
            "commission": self.commission,
            "cost_basis": round(self.cost_basis, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "realized_pnl_pct": self.realized_pnl_pct,
            "trade_id": self.trade_id,
            "reasoning": self.reasoning,
        }


@dataclass
class LedgerBuyRow:
    date: str
    at: str
    code: str
    name: str
    shares: int
    price: float
    amount: float
    commission: float
    trade_id: Optional[str] = None
    decision_action: Optional[str] = None
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "at": self.at,
            "side": "buy",
            "code": self.code,
            "name": self.name,
            "shares": self.shares,
            "price": self.price,
            "buy_price": self.price,
            "amount": self.amount,
            "commission": self.commission,
            "trade_id": self.trade_id,
            "decision_action": self.decision_action,
            "reasoning": self.reasoning,
        }


@dataclass
class PnlOverview:
    as_of: str
    period_start: str
    period_end: str
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    trade_cash_flow: float
    realized_sells: list[RealizedSellRow] = field(default_factory=list)
    buys: list[LedgerBuyRow] = field(default_factory=list)
    win_count: int = 0
    loss_count: int = 0
    flat_count: int = 0
    holdings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "trade_cash_flow": round(self.trade_cash_flow, 2),
            "realized_sells": [r.to_dict() for r in self.realized_sells],
            "buys": [b.to_dict() for b in self.buys],
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "flat_count": self.flat_count,
            "holdings": self.holdings,
        }


def load_ledger_entries(
    *,
    path: Optional[Path] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> list[dict[str, Any]]:
    p = path or default_ledger_path()
    if not p.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        at = str(entry.get("at") or "")
        day = at[:10]
        if start is not None and day and day < start.isoformat():
            continue
        if end is not None and day and day > end.isoformat():
            continue
        entries.append(entry)
    return dedupe_trade_ledger_entries(entries)


def format_trade_at(iso_at: str) -> str:
    """Format ledger ISO timestamp for display (Asia/Shanghai)."""
    raw = str(iso_at or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return raw[:16].replace("T", " ")


def _ledger_buy_rows(trades: list[dict[str, Any]]) -> list[LedgerBuyRow]:
    rows: list[LedgerBuyRow] = []
    for entry in trades:
        entry_at = str(entry.get("at") or "")
        day = entry_at[:10]
        trade_id = entry.get("trade_id")
        decision = entry.get("decision_action")
        for action in entry.get("actions") or []:
            if action.get("side") != "buy":
                continue
            shares = int(action.get("shares") or 0)
            if shares <= 0:
                continue
            rows.append(
                LedgerBuyRow(
                    date=day,
                    at=entry_at,
                    code=_normalize_code(str(action.get("code") or "")),
                    name=str(action.get("name") or action.get("code") or "?"),
                    shares=shares,
                    price=float(action.get("price") or 0),
                    amount=float(action.get("amount") or 0),
                    commission=float(action.get("commission") or 0),
                    trade_id=str(trade_id) if trade_id else None,
                    decision_action=str(decision) if decision else None,
                    reasoning=str(action.get("reasoning") or ""),
                )
            )
    return rows


def _latest_buys_by_code(buys: list[LedgerBuyRow]) -> dict[str, LedgerBuyRow]:
    out: dict[str, LedgerBuyRow] = {}
    for row in buys:
        if row.code:
            out[row.code] = row
    return out


def format_buy_trade_line(row: dict[str, Any] | LedgerBuyRow) -> str:
    data = row.to_dict() if isinstance(row, LedgerBuyRow) else row
    name = data.get("name") or data.get("code") or "?"
    code = data.get("code") or "?"
    shares = int(data.get("shares") or 0)
    price = float(data.get("price") or data.get("buy_price") or 0)
    commission = float(data.get("commission") or 0)
    when = format_trade_at(str(data.get("at") or "")) or str(data.get("date") or "")
    parts = [
        f"买入 **{name}** ({code})",
        f"{shares}股 @ ¥{price:.2f}",
        f"成交额 ¥{float(data.get('amount') or 0):,.0f}",
    ]
    if commission:
        parts.append(f"佣金 ¥{commission:.2f}")
    if when:
        parts.append(when)
    trade_id = data.get("trade_id")
    if trade_id:
        parts.append(f"#{trade_id}")
    return " · ".join(parts)


def format_sell_trade_line(row: dict[str, Any] | RealizedSellRow) -> str:
    data = row.to_dict() if isinstance(row, RealizedSellRow) else row
    name = data.get("name") or data.get("code") or "?"
    code = data.get("code") or "?"
    shares = int(data.get("shares") or 0)
    sell_px = float(data.get("price") or data.get("sell_price") or 0)
    buy_px = data.get("avg_buy_price")
    pnl = float(data.get("realized_pnl") or 0)
    pct = data.get("realized_pnl_pct")
    when = format_trade_at(str(data.get("at") or "")) or str(data.get("date") or "")
    px_part = f"卖 ¥{sell_px:.2f}"
    if buy_px is not None:
        px_part = f"买 ¥{float(buy_px):.2f} → {px_part}"
    pct_s = f"（{float(pct):+.2f}%）" if pct is not None else ""
    parts = [
        f"卖出 **{name}** ({code})",
        f"{shares}股",
        px_part,
        f"已实现 **{pnl:+,.0f}**{pct_s}",
    ]
    commission = float(data.get("commission") or 0)
    if commission:
        parts.append(f"佣金 ¥{commission:.2f}")
    if when:
        parts.append(when)
    trade_id = data.get("trade_id")
    if trade_id:
        parts.append(f"#{trade_id}")
    return " · ".join(parts)


def format_holding_trade_line(row: dict[str, Any]) -> str:
    name = row.get("name") or row.get("code") or "?"
    code = row.get("code") or "?"
    shares = int(row.get("shares") or 0)
    buy_px = row.get("buy_price")
    if buy_px is None:
        buy_px = row.get("cost")
    close_px = row.get("price")
    pnl = float(row.get("unrealized_pnl") or 0)
    pct = row.get("unrealized_pnl_pct")
    pct_s = f"（{float(pct):+.2f}%）" if pct is not None else ""
    parts = [f"**{name}** ({code})", f"{shares}股"]
    if buy_px is not None and close_px is not None:
        parts.append(f"买 ¥{float(buy_px):.2f} → 现 ¥{float(close_px):.2f}")
    elif close_px is not None:
        parts.append(f"现价 ¥{float(close_px):.2f}")
    parts.append(f"浮盈浮亏 **{pnl:+,.0f}**{pct_s}")
    when = row.get("buy_at")
    if when:
        parts.append(f"买入 {format_trade_at(str(when)) or str(when)[:10]}")
    return " · ".join(parts)


def compute_trade_cash_flow(trades: list[dict[str, Any]]) -> float:
    """Net cash flow from ledger (sell proceeds − buy costs − commissions)."""
    pnl = 0.0
    for entry in trades:
        for action in entry.get("actions") or []:
            side = action.get("side")
            amount = float(action.get("amount") or 0)
            commission = float(action.get("commission") or 0)
            if side == "sell":
                pnl += amount - commission
            elif side == "buy":
                pnl -= amount + commission
    return round(pnl, 2)


def _lot_shares(queue: deque[tuple[int, float, str]]) -> int:
    return sum(shares for shares, _, _ in queue)


def _lot_tuple(shares: int, cost_per: float, buy_date: str = "") -> tuple[int, float, str]:
    return (shares, cost_per, buy_date)


def _lot_buy_date(lot: tuple[int, float, str] | tuple[int, float]) -> str:
    if len(lot) >= 3:
        return str(lot[2] or "")
    return ""


def opening_costs_from_portfolio(portfolio: Optional[dict[str, Any]]) -> dict[str, float]:
    """Map normalized code -> per-share cost for legacy FIFO seeding."""
    out: dict[str, float] = {}
    for row in (portfolio or {}).get("holdings") or []:
        code = _normalize_code(str(row.get("code") or ""))
        cost = float(row.get("cost") or 0)
        if code and cost > 0:
            out[code] = cost
    return out


def _resolve_holding_cost_per_share(
    action: dict[str, Any],
    *,
    opening_costs: Optional[dict[str, float]] = None,
) -> float:
    for key in ("holding_cost", "cost_per_share", "cost"):
        raw = action.get(key)
        if raw is not None and float(raw) > 0:
            return float(raw)
    code = _normalize_code(str(action.get("code") or ""))
    if opening_costs and code in opening_costs:
        return float(opening_costs[code])
    return 0.0


def _seed_lot_if_needed(
    lots: dict[str, deque[tuple[int, float, str]]],
    code: str,
    *,
    shares_needed: int,
    cost_per_share: float,
) -> None:
    if shares_needed <= 0 or cost_per_share <= 0:
        return
    queue = lots.setdefault(code, deque())
    have = _lot_shares(queue)
    if have >= shares_needed:
        return
    missing = shares_needed - have
    queue.appendleft(_lot_tuple(missing, float(cost_per_share), ""))


def _apply_buy(
    lots: dict[str, deque[tuple[int, float, str]]],
    action: dict[str, Any],
    *,
    buy_date: str,
) -> None:
    shares = int(action.get("shares") or 0)
    amount = float(action.get("amount") or 0)
    commission = float(action.get("commission") or 0)
    if shares <= 0:
        return
    code = _normalize_code(str(action.get("code") or "__unknown__"))
    cost_per = (amount + commission) / shares
    lots.setdefault(code, deque()).append(_lot_tuple(shares, cost_per, buy_date))


def _apply_sell(
    lots: dict[str, deque[tuple[int, float, str]]],
    action: dict[str, Any],
    *,
    sell_date: str,
    opening_costs: Optional[dict[str, float]] = None,
) -> tuple[float, float]:
    """Return (realized_pnl, cost_basis) for one sell action."""
    shares = int(action.get("shares") or 0)
    amount = float(action.get("amount") or 0)
    commission = float(action.get("commission") or 0)
    if shares <= 0:
        amount_only = amount - commission if amount else 0.0
        return round(amount_only, 2), 0.0

    code = _normalize_code(str(action.get("code") or "__unknown__"))
    cost_per = _resolve_holding_cost_per_share(action, opening_costs=opening_costs)
    if cost_per > 0:
        _seed_lot_if_needed(lots, code, shares_needed=shares, cost_per_share=cost_per)

    proceeds_per = (amount - commission) / shares
    remaining = shares
    queue = lots.setdefault(code, deque())
    rest: deque[tuple[int, float, str]] = deque()
    pnl = 0.0
    cost_basis = 0.0
    while remaining > 0:
        if not queue:
            break
        lot_shares, lot_cost, lot_date = queue.popleft()
        if lot_date and lot_date == sell_date:
            rest.append(_lot_tuple(lot_shares, lot_cost, lot_date))
            continue
        take = min(remaining, lot_shares)
        pnl += take * (proceeds_per - lot_cost)
        cost_basis += take * lot_cost
        remaining -= take
        if lot_shares > take:
            rest.appendleft(_lot_tuple(lot_shares - take, lot_cost, lot_date))
    rest.extend(queue)
    lots[code] = rest
    if remaining > 0:
        fallback_cost = cost_per if cost_per > 0 else float(action.get("price") or 0)
        if fallback_cost > 0:
            pnl += remaining * (proceeds_per - fallback_cost)
            cost_basis += remaining * fallback_cost
    return round(pnl, 2), round(cost_basis, 2)


def replay_realized_sells(
    trades: list[dict[str, Any]],
    *,
    opening_costs: Optional[dict[str, float]] = None,
) -> list[RealizedSellRow]:
    """FIFO replay: one row per sell with realized P&L."""
    lots: dict[str, deque[tuple[int, float, str]]] = {}
    rows: list[RealizedSellRow] = []

    for entry in trades:
        actions = list(entry.get("actions") or [])
        entry_at = str(entry.get("at") or "")
        at = entry_at[:10]
        trade_id = entry.get("trade_id")

        if (
            actions
            and any(a.get("side") == "buy" for a in actions)
            and any(a.get("side") == "sell" for a in actions)
            and all(int(a.get("shares") or 0) <= 0 for a in actions)
        ):
            cash_pnl = compute_trade_cash_flow([entry])
            for action in actions:
                if action.get("side") != "sell":
                    continue
                rows.append(
                    RealizedSellRow(
                        date=at,
                        at=entry_at,
                        code=_normalize_code(str(action.get("code") or "")),
                        name=str(action.get("name") or action.get("code") or "?"),
                        shares=int(action.get("shares") or 0),
                        price=float(action.get("price") or 0),
                        amount=float(action.get("amount") or 0),
                        commission=float(action.get("commission") or 0),
                        cost_basis=0.0,
                        realized_pnl=cash_pnl,
                        trade_id=str(trade_id) if trade_id else None,
                        reasoning=str(action.get("reasoning") or ""),
                        avg_buy_price=None,
                    )
                )
            continue

        orphan_sells: list[dict[str, Any]] = []
        for action in actions:
            side = action.get("side")
            if side == "buy":
                _apply_buy(lots, action, buy_date=at)
            elif side == "sell":
                if int(action.get("shares") or 0) > 0:
                    orphan_sells.append(action)
                else:
                    amount = float(action.get("amount") or 0)
                    commission = float(action.get("commission") or 0)
                    rows.append(
                        RealizedSellRow(
                            date=at,
                            at=entry_at,
                            code=_normalize_code(str(action.get("code") or "")),
                            name=str(action.get("name") or action.get("code") or "?"),
                            shares=0,
                            price=float(action.get("price") or 0),
                            amount=amount,
                            commission=commission,
                            cost_basis=0.0,
                            realized_pnl=round(amount - commission, 2),
                            trade_id=str(trade_id) if trade_id else None,
                            reasoning=str(action.get("reasoning") or ""),
                            avg_buy_price=None,
                        )
                    )

        for action in orphan_sells:
            realized, cost_basis = _apply_sell(
                lots,
                action,
                sell_date=at,
                opening_costs=opening_costs,
            )
            shares = int(action.get("shares") or 0)
            pct = round(realized / cost_basis * 100, 2) if cost_basis > 0 else None
            avg_buy = round(cost_basis / shares, 4) if shares > 0 and cost_basis > 0 else None
            rows.append(
                RealizedSellRow(
                    date=at,
                    at=entry_at,
                    code=_normalize_code(str(action.get("code") or "")),
                    name=str(action.get("name") or action.get("code") or "?"),
                    shares=shares,
                    price=float(action.get("price") or 0),
                    amount=float(action.get("amount") or 0),
                    commission=float(action.get("commission") or 0),
                    cost_basis=cost_basis,
                    realized_pnl=realized,
                    realized_pnl_pct=pct,
                    trade_id=str(trade_id) if trade_id else None,
                    reasoning=str(action.get("reasoning") or ""),
                    avg_buy_price=avg_buy,
                )
            )
    return rows


def compute_realized_pnl(
    trades: list[dict[str, Any]],
    *,
    opening_costs: Optional[dict[str, float]] = None,
) -> float:
    return round(
        sum(r.realized_pnl for r in replay_realized_sells(trades, opening_costs=opening_costs)),
        2,
    )


def sum_stored_realized_pnl(trades: list[dict[str, Any]]) -> Optional[float]:
    """Sum ``realized_pnl`` stamped on sell actions at persist time (authoritative when present)."""
    total = 0.0
    found = False
    for entry in trades:
        for action in entry.get("actions") or []:
            if action.get("side") != "sell":
                continue
            if action.get("realized_pnl") is None:
                continue
            total += float(action["realized_pnl"])
            found = True
    return round(total, 2) if found else None


def compute_day_realized_pnl(
    day_trades: list[dict[str, Any]],
    *,
    prior_trades: Optional[list[dict[str, Any]]] = None,
    opening_costs: Optional[dict[str, float]] = None,
    use_stored: bool = True,
) -> float:
    """Day realized P&L: prefer stored sell fields, else FIFO replay with buy history."""
    if use_stored:
        stored = sum_stored_realized_pnl(day_trades)
        if stored is not None:
            return stored
    merged = list(prior_trades or []) + list(day_trades or [])
    if not merged:
        return 0.0
    day_s = str(day_trades[0].get("at") or "")[:10] if day_trades else ""
    if not day_s and day_trades:
        day_s = ""
    rows = replay_realized_sells(merged, opening_costs=opening_costs)
    if day_s:
        rows = [r for r in rows if r.date == day_s]
    return round(sum(r.realized_pnl for r in rows), 2)


def annotate_ledger_sell_pnl(
    entries: list[dict[str, Any]],
    *,
    prior_trades: Optional[list[dict[str, Any]]] = None,
    opening_costs: Optional[dict[str, float]] = None,
) -> list[dict[str, Any]]:
    """Overwrite sell action realized_pnl fields using FIFO replay (for display / close cards)."""
    merged = list(prior_trades or []) + list(entries or [])
    rows = replay_realized_sells(merged, opening_costs=opening_costs)
    row_idx = 0
    out: list[dict[str, Any]] = []
    for entry in entries:
        at = str(entry.get("at") or "")[:10]
        new_actions: list[dict[str, Any]] = []
        for action in entry.get("actions") or []:
            act = dict(action)
            if action.get("side") == "sell" and int(action.get("shares") or 0) > 0:
                code = _normalize_code(str(action.get("code") or ""))
                shares = int(action.get("shares") or 0)
                while row_idx < len(rows) and not (
                    rows[row_idx].date == at
                    and _normalize_code(rows[row_idx].code) == code
                    and int(rows[row_idx].shares or 0) == shares
                ):
                    row_idx += 1
                if row_idx < len(rows):
                    sell_row = rows[row_idx]
                    row_idx += 1
                    act["cost_basis"] = sell_row.cost_basis
                    act["realized_pnl"] = sell_row.realized_pnl
                    if sell_row.realized_pnl_pct is not None:
                        act["realized_pnl_pct"] = sell_row.realized_pnl_pct
            new_actions.append(act)
        out.append({**dict(entry), "actions": new_actions})
    return out


def opening_costs_for_display() -> dict[str, float]:
    """Morning baseline costs, with current portfolio filling gaps only."""
    costs: dict[str, float] = {}
    try:
        from agent_reach.daily_run.workflows import load_morning_baseline

        costs.update(
            opening_costs_from_portfolio((load_morning_baseline().get("portfolio") or {}))
        )
    except FileNotFoundError:
        pass
    try:
        from agent_reach.daily_run.snapshot_builder import load_portfolio

        for code, cost in opening_costs_from_portfolio(load_portfolio()).items():
            costs.setdefault(code, cost)
    except Exception:
        pass
    return costs


def enrich_sell_actions_for_display(
    actions: list[dict[str, Any]],
    *,
    entry_at: str,
    prior_trades: Optional[list[dict[str, Any]]] = None,
    opening_costs: Optional[dict[str, float]] = None,
) -> list[dict[str, Any]]:
    """Fill missing realized_pnl on sell rows for intraday / close display."""
    sells = [a for a in actions if a.get("side") == "sell" and a.get("realized_pnl") is None]
    if not sells:
        return [dict(a) for a in actions]
    if prior_trades is None:
        prior_trades = [
            e
            for e in load_ledger_entries(end=today_shanghai())
            if str(e.get("at") or "") < entry_at
        ]
    costs = opening_costs if opening_costs is not None else opening_costs_for_display()
    return enrich_sell_actions(
        prior_trades,
        [dict(a) for a in actions],
        entry_at=entry_at,
        opening_costs=costs or None,
    )


def enrich_sell_actions(
    prior_entries: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    *,
    entry_at: str,
    trade_id: Optional[str] = None,
    opening_costs: Optional[dict[str, float]] = None,
) -> list[dict[str, Any]]:
    """Annotate sell actions with realized_pnl fields before persisting."""
    synthetic = prior_entries + [
        {
            "at": entry_at,
            "trade_id": trade_id,
            "actions": actions,
        }
    ]
    rows = replay_realized_sells(synthetic, opening_costs=opening_costs)
    new_sells = [r for r in rows if r.date == entry_at[:10]]
    sell_map: dict[str, RealizedSellRow] = {}
    for row in new_sells:
        key = "|".join(
            [
                row.code,
                str(row.shares),
                f"{row.price:.4f}",
                f"{row.amount:.2f}",
            ]
        )
        sell_map[key] = row

    enriched: list[dict[str, Any]] = []
    for action in actions:
        row = dict(action)
        if action.get("side") != "sell":
            enriched.append(row)
            continue
        key = "|".join(
            [
                _normalize_code(str(action.get("code") or "")),
                str(int(action.get("shares") or 0)),
                f"{float(action.get('price') or 0):.4f}",
                f"{float(action.get('amount') or 0):.2f}",
            ]
        )
        sell_row = sell_map.get(key)
        if sell_row:
            row["cost_basis"] = sell_row.cost_basis
            row["realized_pnl"] = sell_row.realized_pnl
            if sell_row.realized_pnl_pct is not None:
                row["realized_pnl_pct"] = sell_row.realized_pnl_pct
        enriched.append(row)
    return enriched


def _holding_unrealized_rows(
    portfolio: dict[str, Any],
    *,
    latest_buys: dict[str, LedgerBuyRow] | None = None,
) -> list[dict[str, Any]]:
    latest_buys = latest_buys or {}
    rows: list[dict[str, Any]] = []
    for h in portfolio.get("holdings") or []:
        code = _normalize_code(str(h.get("code") or ""))
        shares = int(h.get("shares") or 0)
        buy = latest_buys.get(code)
        cost = float(h.get("cost") or 0)
        if cost <= 0 and buy:
            cost = float(buy.price)
        price = float(h.get("price") or cost)
        cost_basis = round(shares * cost, 2)
        mv = round(shares * price, 2)
        unrealized = round(mv - cost_basis, 2)
        pct = round(unrealized / cost_basis * 100, 2) if cost_basis > 0 else None
        row: dict[str, Any] = {
            "code": code,
            "name": h.get("name") or code,
            "shares": shares,
            "cost": cost,
            "price": price,
            "cost_basis": cost_basis,
            "market_value": mv,
            "unrealized_pnl": unrealized,
            "unrealized_pnl_pct": pct,
        }
        if buy:
            row["buy_at"] = buy.at
            row["buy_price"] = round(buy.price, 4)
            row["buy_shares"] = buy.shares
        elif h.get("acquired_date"):
            row["buy_at"] = str(h.get("acquired_date") or "")
        rows.append(row)
    rows.sort(key=lambda x: abs(float(x.get("unrealized_pnl") or 0)), reverse=True)
    return rows


def build_pnl_overview(
    portfolio: Optional[dict[str, Any]] = None,
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
    ledger_path: Optional[Path] = None,
) -> PnlOverview:
    day = end or today_shanghai()
    period_start = start or day
    entries = load_ledger_entries(path=ledger_path, start=period_start, end=day)
    buy_rows = _ledger_buy_rows(entries)
    latest_buys = _latest_buys_by_code(buy_rows)
    pf = portfolio or {}
    seed_costs = opening_costs_from_portfolio(pf)
    realized_rows = replay_realized_sells(entries, opening_costs=seed_costs or None)
    realized = round(sum(r.realized_pnl for r in realized_rows), 2)
    cash_flow = compute_trade_cash_flow(entries)

    holdings = _holding_unrealized_rows(pf, latest_buys=latest_buys)
    unrealized = round(sum(float(h.get("unrealized_pnl") or 0) for h in holdings), 2)

    wins = losses = flats = 0
    for row in realized_rows:
        if row.realized_pnl > 0.01:
            wins += 1
        elif row.realized_pnl < -0.01:
            losses += 1
        else:
            flats += 1

    return PnlOverview(
        as_of=day.isoformat(),
        period_start=period_start.isoformat(),
        period_end=day.isoformat(),
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        total_pnl=round(realized + unrealized, 2),
        trade_cash_flow=cash_flow,
        realized_sells=realized_rows,
        buys=buy_rows,
        win_count=wins,
        loss_count=losses,
        flat_count=flats,
        holdings=holdings,
    )


def render_pnl_overview_markdown(overview: PnlOverview | dict[str, Any]) -> str:
    data = overview.to_dict() if isinstance(overview, PnlOverview) else overview
    lines: list[str] = ["## 📊 盈亏总览"]

    realized = float(data.get("realized_pnl") or 0)
    unrealized = float(data.get("unrealized_pnl") or 0)
    total = float(data.get("total_pnl") or 0)
    lines.append(
        f"- **总收益** {total:+,.0f} = **历史已实现** {realized:+,.0f} + **当前持股** {unrealized:+,.0f}"
    )
    wins = int(data.get("win_count") or 0)
    losses = int(data.get("loss_count") or 0)
    if wins or losses:
        lines.append(f"- 卖出统计：{wins} 盈 / {losses} 亏")

    sells = data.get("realized_sells") or []
    buys = data.get("buys") or []
    if buys:
        lines.append("")
        lines.append("### 买入记录")
        for row in buys:
            lines.append(f"- {format_buy_trade_line(row)}")

    lines.append("")
    lines.append("### 已实现（卖出）")
    if sells:
        for row in sells:
            lines.append(f"- {format_sell_trade_line(row)}")
    else:
        lines.append("- 暂无卖出记录")

    holdings = data.get("holdings") or []
    lines.append("")
    lines.append("### 浮动（持仓）")
    if holdings:
        for h in holdings:
            lines.append(f"- {format_holding_trade_line(h)}")
    else:
        lines.append("- 当前无持仓")

    return "\n".join(lines).strip()


def backfill_ledger_realized_pnl(*, path: Optional[Path] = None, dry_run: bool = False) -> dict[str, Any]:
    """Rewrite ledger lines to add realized_pnl on sell actions (idempotent)."""
    p = path or default_ledger_path()
    if not p.is_file():
        return {"ok": True, "updated": 0, "message": "ledger empty"}

    entries: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    deduped = dedupe_trade_ledger_entries(entries)
    seed_costs: dict[str, float] = {}
    try:
        from agent_reach.daily_run.workflows import load_morning_baseline

        baseline = load_morning_baseline()
        seed_costs = opening_costs_from_portfolio(baseline.get("portfolio") or baseline)
    except Exception:
        seed_costs = {}
    rows = replay_realized_sells(deduped, opening_costs=seed_costs or None)
    row_idx = 0
    updated = 0
    new_lines: list[str] = []

    for entry in deduped:
        at = str(entry.get("at") or "")[:10]
        new_actions: list[dict[str, Any]] = []
        changed = False
        for action in entry.get("actions") or []:
            act = dict(action)
            if action.get("side") == "sell":
                while row_idx < len(rows) and not (
                    rows[row_idx].date == at
                    and _normalize_code(rows[row_idx].code)
                    == _normalize_code(str(action.get("code") or ""))
                    and int(rows[row_idx].shares or 0) == int(action.get("shares") or 0)
                ):
                    row_idx += 1
                if row_idx < len(rows):
                    sell_row = rows[row_idx]
                    row_idx += 1
                    if act.get("realized_pnl") != sell_row.realized_pnl:
                        changed = True
                    act["cost_basis"] = sell_row.cost_basis
                    act["realized_pnl"] = sell_row.realized_pnl
                    if sell_row.realized_pnl_pct is not None:
                        act["realized_pnl_pct"] = sell_row.realized_pnl_pct
            new_actions.append(act)
        if changed:
            updated += 1
        out_entry = dict(entry)
        out_entry["actions"] = new_actions
        new_lines.append(json.dumps(out_entry, ensure_ascii=False))

    if not dry_run and updated:
        p.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")

    return {"ok": True, "updated": updated, "path": str(p), "dry_run": dry_run}

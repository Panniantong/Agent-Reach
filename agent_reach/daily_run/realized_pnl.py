# -*- coding: utf-8
"""FIFO realized P&L from trade ledger + portfolio overview."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "code": self.code,
            "name": self.name,
            "shares": self.shares,
            "price": self.price,
            "amount": self.amount,
            "commission": self.commission,
            "cost_basis": round(self.cost_basis, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "realized_pnl_pct": self.realized_pnl_pct,
            "trade_id": self.trade_id,
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


def _apply_buy(lots: dict[str, deque[tuple[int, float]]], action: dict[str, Any]) -> None:
    shares = int(action.get("shares") or 0)
    amount = float(action.get("amount") or 0)
    commission = float(action.get("commission") or 0)
    if shares <= 0:
        return
    code = _normalize_code(str(action.get("code") or "__unknown__"))
    cost_per = (amount + commission) / shares
    lots.setdefault(code, deque()).append((shares, cost_per))


def _apply_sell(
    lots: dict[str, deque[tuple[int, float]]],
    action: dict[str, Any],
) -> tuple[float, float]:
    """Return (realized_pnl, cost_basis) for one sell action."""
    shares = int(action.get("shares") or 0)
    amount = float(action.get("amount") or 0)
    commission = float(action.get("commission") or 0)
    if shares <= 0:
        amount_only = amount - commission if amount else 0.0
        return round(amount_only, 2), 0.0

    code = _normalize_code(str(action.get("code") or "__unknown__"))
    proceeds_per = (amount - commission) / shares
    remaining = shares
    queue = lots.setdefault(code, deque())
    pnl = 0.0
    cost_basis = 0.0
    while remaining > 0 and queue:
        lot_shares, lot_cost = queue[0]
        take = min(remaining, lot_shares)
        pnl += take * (proceeds_per - lot_cost)
        cost_basis += take * lot_cost
        remaining -= take
        if take >= lot_shares:
            queue.popleft()
        else:
            queue[0] = (lot_shares - take, lot_cost)
    if remaining > 0:
        fallback_cost = float(action.get("price") or 0)
        if fallback_cost > 0:
            pnl += remaining * (proceeds_per - fallback_cost)
            cost_basis += remaining * fallback_cost
    return round(pnl, 2), round(cost_basis, 2)


def replay_realized_sells(trades: list[dict[str, Any]]) -> list[RealizedSellRow]:
    """FIFO replay: one row per sell with realized P&L."""
    lots: dict[str, deque[tuple[int, float]]] = {}
    rows: list[RealizedSellRow] = []

    for entry in trades:
        actions = list(entry.get("actions") or [])
        at = str(entry.get("at") or "")[:10]
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
                    )
                )
            continue

        orphan_sells: list[dict[str, Any]] = []
        for action in actions:
            side = action.get("side")
            if side == "buy":
                _apply_buy(lots, action)
            elif side == "sell":
                if int(action.get("shares") or 0) > 0:
                    orphan_sells.append(action)
                else:
                    amount = float(action.get("amount") or 0)
                    commission = float(action.get("commission") or 0)
                    rows.append(
                        RealizedSellRow(
                            date=at,
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
                        )
                    )

        for action in orphan_sells:
            realized, cost_basis = _apply_sell(lots, action)
            shares = int(action.get("shares") or 0)
            pct = round(realized / cost_basis * 100, 2) if cost_basis > 0 else None
            rows.append(
                RealizedSellRow(
                    date=at,
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
                )
            )
    return rows


def compute_realized_pnl(trades: list[dict[str, Any]]) -> float:
    return round(sum(r.realized_pnl for r in replay_realized_sells(trades)), 2)


def enrich_sell_actions(
    prior_entries: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    *,
    entry_at: str,
    trade_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Annotate sell actions with realized_pnl fields before persisting."""
    synthetic = prior_entries + [
        {
            "at": entry_at,
            "trade_id": trade_id,
            "actions": actions,
        }
    ]
    rows = replay_realized_sells(synthetic)
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


def _holding_unrealized_rows(portfolio: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for h in portfolio.get("holdings") or []:
        code = _normalize_code(str(h.get("code") or ""))
        shares = int(h.get("shares") or 0)
        cost = float(h.get("cost") or 0)
        price = float(h.get("price") or cost)
        cost_basis = round(shares * cost, 2)
        mv = round(shares * price, 2)
        unrealized = round(mv - cost_basis, 2)
        pct = round(unrealized / cost_basis * 100, 2) if cost_basis > 0 else None
        rows.append(
            {
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
        )
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
    realized_rows = replay_realized_sells(entries)
    realized = round(sum(r.realized_pnl for r in realized_rows), 2)
    cash_flow = compute_trade_cash_flow(entries)

    pf = portfolio or {}
    holdings = _holding_unrealized_rows(pf)
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
        f"- **已实现** {realized:+,.0f} · **浮动** {unrealized:+,.0f} · **合计** {total:+,.0f}"
    )
    wins = int(data.get("win_count") or 0)
    losses = int(data.get("loss_count") or 0)
    if wins or losses:
        lines.append(f"- 卖出统计：{wins} 盈 / {losses} 亏")

    sells = data.get("realized_sells") or []
    lines.append("")
    lines.append("### 已实现（卖出）")
    if sells:
        for row in sells:
            name = row.get("name") or row.get("code")
            code = row.get("code") or "?"
            pnl = float(row.get("realized_pnl") or 0)
            pct = row.get("realized_pnl_pct")
            pct_s = f"（{float(pct):+.2f}%）" if pct is not None else ""
            lines.append(
                f"- **{name}** ({code}) {row.get('shares')}股 · "
                f"盈亏 **{pnl:+,.0f}**{pct_s}"
            )
    else:
        lines.append("- 暂无卖出记录")

    holdings = data.get("holdings") or []
    lines.append("")
    lines.append("### 浮动（持仓）")
    if holdings:
        for h in holdings:
            pnl = float(h.get("unrealized_pnl") or 0)
            pct = h.get("unrealized_pnl_pct")
            pct_s = f"（{float(pct):+.2f}%）" if pct is not None else ""
            lines.append(
                f"- **{h.get('name')}** ({h.get('code')}) · 浮盈浮亏 **{pnl:+,.0f}**{pct_s}"
            )
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
    rows = replay_realized_sells(deduped)
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

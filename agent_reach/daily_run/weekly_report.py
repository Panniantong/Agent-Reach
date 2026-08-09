# -*- coding: utf-8
"""Weekly trading summary — PnL, holdings, watchlist, hot sectors, sector analysis."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.portfolio_manager import default_ledger_path
from agent_reach.daily_run.portfolio_manager import dedupe_trade_ledger_entries
from agent_reach.daily_run.run_manifest import runs_dir
from agent_reach.daily_run.snapshot_builder import _normalize_code
from agent_reach.daily_run.symbols import build_enriched_symbols
from agent_reach.daily_run.trade_calendar import today_shanghai


@dataclass
class WeeklyReport:
    week_start: date
    week_end: date
    start_total: Optional[float]
    end_total: Optional[float]
    weekly_pnl: Optional[float]
    weekly_pnl_pct: Optional[float]
    realized_pnl: float
    trade_cash_flow: float = 0.0
    start_cash: Optional[float] = None
    end_cash: Optional[float] = None
    start_stock_mv: Optional[float] = None
    end_stock_mv: Optional[float] = None
    stock_pnl: Optional[float] = None
    cash_pnl: Optional[float] = None
    holdings: list[dict[str, Any]] = field(default_factory=list)
    watchlist: list[dict[str, Any]] = field(default_factory=list)
    hot_sectors: list[dict[str, Any]] = field(default_factory=list)
    sector_groups: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    trades: list[dict[str, Any]] = field(default_factory=list)
    mss_summary: list[dict[str, Any]] = field(default_factory=list)
    experience_snippets: list[str] = field(default_factory=list)
    sector_research: list[dict[str, Any]] = field(default_factory=list)
    skill_learning: list[dict[str, Any]] = field(default_factory=list)
    skill_research: list[dict[str, Any]] = field(default_factory=list)
    process_improvements: list[dict[str, Any]] = field(default_factory=list)
    watchlist_candidates_update: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    cash: Optional[float] = None
    cash_ratio: Optional[float] = None
    daily_totals: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_start": self.week_start.isoformat(),
            "week_end": self.week_end.isoformat(),
            "start_total": self.start_total,
            "end_total": self.end_total,
            "weekly_pnl": self.weekly_pnl,
            "weekly_pnl_pct": self.weekly_pnl_pct,
            "realized_pnl": self.realized_pnl,
            "trade_cash_flow": self.trade_cash_flow,
            "start_cash": self.start_cash,
            "end_cash": self.end_cash,
            "start_stock_mv": self.start_stock_mv,
            "end_stock_mv": self.end_stock_mv,
            "stock_pnl": self.stock_pnl,
            "cash_pnl": self.cash_pnl,
            "holdings": self.holdings,
            "watchlist": self.watchlist,
            "hot_sectors": self.hot_sectors,
            "sector_groups": self.sector_groups,
            "trades": self.trades,
            "mss_summary": self.mss_summary,
            "experience_snippets": self.experience_snippets,
            "sector_research": self.sector_research,
            "skill_learning": self.skill_learning,
            "skill_research": self.skill_research,
            "process_improvements": self.process_improvements,
            "watchlist_candidates_update": self.watchlist_candidates_update,
            "notes": self.notes,
            "cash": self.cash,
            "cash_ratio": self.cash_ratio,
            "daily_totals": self.daily_totals,
        }


def trading_week_range(as_of: Optional[date] = None) -> tuple[date, date]:
    """Mon–Fri of the trading week ending on the most recent Friday (Saturday report = just-finished week)."""
    d = as_of or today_shanghai()
    if d.weekday() >= 5:
        friday = d - timedelta(days=d.weekday() - 4)
    else:
        friday = d - timedelta(days=d.weekday() - 4) if d.weekday() <= 4 else d
    monday = friday - timedelta(days=4)
    return monday, friday


def _date_in_range(ds: str, start: date, end: date) -> bool:
    try:
        d = date.fromisoformat(ds[:10])
    except ValueError:
        return False
    return start <= d <= end


def _iter_manifest_files(start: date, end: date) -> list[tuple[date, Path]]:
    root = runs_dir()
    if not root.exists():
        return []
    out: list[tuple[date, Path]] = []
    for day_dir in sorted(root.iterdir()):
        if not day_dir.is_dir():
            continue
        try:
            day = date.fromisoformat(day_dir.name)
        except ValueError:
            continue
        if not (start <= day <= end):
            continue
        for path in sorted(day_dir.glob("*.json")):
            out.append((day, path))
    return out


def _load_manifest(path: Path) -> Optional[dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _snapshot_from_manifest(record: dict[str, Any]) -> Optional[dict[str, Any]]:
    payload = record.get("payload") or {}
    result = payload.get("result") or {}
    snap = result.get("snapshot")
    if isinstance(snap, dict):
        return snap
    symbol_results = payload.get("symbol_results") or []
    for sr in reversed(symbol_results):
        snap = (sr.get("result") or {}).get("snapshot")
        if isinstance(snap, dict):
            return snap
    return None


def _portfolio_summary_from_manifest(record: dict[str, Any]) -> Optional[dict[str, Any]]:
    payload = record.get("payload") or {}
    result = payload.get("result") or {}
    ps = result.get("portfolio_summary")
    if isinstance(ps, dict):
        return ps
    for sr in payload.get("symbol_results") or []:
        ps = (sr.get("result") or {}).get("portfolio_summary")
        if isinstance(ps, dict):
            return ps
    return None


def _merged_enriched_from_manifest(
    record: dict[str, Any],
) -> tuple[Optional[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Base snapshot plus merged live prices from all per-symbol runs in one manifest."""
    payload = record.get("payload") or {}
    symbol_results = payload.get("symbol_results") or []
    if symbol_results:
        base = dict((symbol_results[-1].get("result") or {}).get("snapshot") or {})
        if not base:
            return None, {}
        enriched = build_enriched_symbols(base)
        for sr in symbol_results:
            snap = (sr.get("result") or {}).get("snapshot") or {}
            code = _normalize_code(str(snap.get("code") or sr.get("code") or ""))
            if code and snap.get("price") is not None:
                enriched.setdefault(code, {})["price"] = float(snap["price"])
        return base, enriched
    snap = _snapshot_from_manifest(record)
    if snap:
        return snap, build_enriched_symbols(snap)
    return None, {}


def _recalc_total_from_enriched(
    portfolio: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
) -> float:
    """Mark-to-market total using live enriched prices (not cost basis on holdings)."""
    cash = float(portfolio.get("cash") or 0)
    return round(cash + _stock_mv_from_enriched(portfolio, enriched), 2)


def _stock_mv_from_enriched(
    portfolio: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
) -> float:
    mv = 0.0
    for h in portfolio.get("holdings") or []:
        code = _normalize_code(str(h.get("code", "")))
        row = enriched.get(code) or {}
        price = row.get("price")
        if price is None:
            price = h.get("price") or h.get("cost") or 0
        mv += int(h.get("shares") or 0) * float(price)
    return round(mv, 2)


def _portfolio_parts_from_manifest(
    record: dict[str, Any],
) -> tuple[Optional[float], Optional[float]]:
    """Return (cash, stock_market_value) from a run manifest."""
    ps = _portfolio_summary_from_manifest(record)
    if ps:
        cash = ps.get("cash")
        stock_mv = ps.get("stock_mv")
        if cash is not None and stock_mv is not None:
            return float(cash), float(stock_mv)

    snap, enriched = _merged_enriched_from_manifest(record)
    if not snap:
        return None, None

    pf = dict(snap.get("portfolio") or {})
    if not pf.get("holdings") and pf.get("cash") is None:
        return None, None

    cash = float(pf.get("cash") or 0)
    return cash, _stock_mv_from_enriched(pf, enriched)


def _start_manifest_record(
    manifests: list[dict[str, Any]],
    morning_totals: list[tuple[str, float]],
    close_totals: list[tuple[str, float]],
    week_start: date,
) -> Optional[dict[str, Any]]:
    if morning_totals:
        day = morning_totals[0][0]
        rows = sorted(
            [m for m in manifests if m.get("_run_date") == day and m.get("job") == "morning"],
            key=_manifest_sort_key,
        )
        if rows:
            return rows[0]
    if close_totals:
        day = close_totals[0][0]
        rows = sorted(
            [m for m in manifests if m.get("_run_date") == day and m.get("job") == "close"],
            key=_manifest_sort_key,
        )
        if rows:
            return rows[0]
    for offset in range(1, 11):
        day = week_start - timedelta(days=offset)
        rows = sorted(
            [m for m in _load_week_manifests(day, day) if m.get("job") == "close"],
            key=_manifest_sort_key,
        )
        if rows:
            return rows[-1]
    return None


def _end_manifest_record(
    manifests: list[dict[str, Any]],
    close_totals: list[tuple[str, float]],
) -> Optional[dict[str, Any]]:
    if not close_totals:
        return None
    day = close_totals[-1][0]
    rows = sorted(
        [m for m in manifests if m.get("_run_date") == day and m.get("job") == "close"],
        key=_manifest_sort_key,
    )
    return rows[-1] if rows else None


def _portfolio_total_from_manifest(record: dict[str, Any]) -> Optional[float]:
    ps = _portfolio_summary_from_manifest(record)
    if ps and ps.get("end_total") is not None:
        return float(ps["end_total"])

    snap, enriched = _merged_enriched_from_manifest(record)
    if not snap:
        return None

    pf = dict(snap.get("portfolio") or {})
    if pf.get("holdings") or pf.get("cash") is not None:
        return _recalc_total_from_enriched(pf, enriched)

    total = pf.get("total")
    if total is not None:
        return float(total)
    if ps and ps.get("start_total") is not None:
        return float(ps["start_total"])
    return None


def _load_prior_close_total(before: date, *, max_days: int = 10) -> Optional[float]:
    """Most recent close manifest total strictly before `before`."""
    for offset in range(1, max_days + 1):
        day = before - timedelta(days=offset)
        day_records = sorted(
            _load_week_manifests(day, day),
            key=_manifest_sort_key,
        )
        for record in reversed(day_records):
            if record.get("job") != "close":
                continue
            total = _portfolio_total_from_manifest(record)
            if total is not None:
                return total
    return None


def _prices_from_snapshot(snap: dict[str, Any]) -> dict[str, float]:
    enriched = build_enriched_symbols(snap)
    prices: dict[str, float] = {}
    for code, row in enriched.items():
        for key in ("price", "cost"):
            val = row.get(key)
            if val is not None:
                prices[code] = float(val)
                break
    return prices


def _prices_from_manifest_record(record: dict[str, Any]) -> dict[str, float]:
    _, enriched = _merged_enriched_from_manifest(record)
    return {
        code: float(row["price"])
        for code, row in enriched.items()
        if row.get("price") is not None
    }


def _week_start_prices_from_manifests(
    manifests: list[dict[str, Any]],
    week_start: date,
) -> tuple[dict[str, float], Optional[str]]:
    """First Mon–Fri morning/close prices on/after week_start; else prior close."""
    ws = week_start.isoformat()
    morning = sorted(
        [m for m in manifests if m.get("job") == "morning"],
        key=lambda m: str(m.get("_run_date") or ""),
    )
    for record in morning:
        day = str(record.get("_run_date") or "")
        if day and day >= ws:
            prices = _prices_from_manifest_record(record)
            if prices:
                return prices, None

    close_rows = sorted(
        [m for m in manifests if m.get("job") == "close"],
        key=lambda m: str(m.get("_run_date") or ""),
    )
    for record in close_rows:
        day = str(record.get("_run_date") or "")
        if day and day >= ws:
            prices = _prices_from_manifest_record(record)
            if prices:
                return prices, "本周无早盘报价 manifest，持股本周盈亏按本周首个收盘 manifest 估算"

    for offset in range(1, 11):
        day = week_start - timedelta(days=offset)
        day_records = sorted(
            [m for m in _load_week_manifests(day, day) if m.get("job") == "close"],
            key=_manifest_sort_key,
        )
        if not day_records:
            continue
        prices = _prices_from_manifest_record(day_records[-1])
        if prices:
            return prices, f"本周无有效报价 manifest，持股本周盈亏按 {day.isoformat()} 收盘价估算"

    return {}, None


def _week_end_prices_from_manifests(
    manifests: list[dict[str, Any]],
    week_end: date,
) -> tuple[dict[str, float], Optional[str]]:
    """Last close prices on/before week_end from week manifests."""
    we = week_end.isoformat()
    close_rows = sorted(
        [m for m in manifests if m.get("job") == "close"],
        key=lambda m: str(m.get("_run_date") or ""),
    )
    candidates = [
        r
        for r in close_rows
        if (day := str(r.get("_run_date") or "")) and day <= we
    ]
    if candidates:
        prices = _prices_from_manifest_record(candidates[-1])
        if prices:
            day = str(candidates[-1].get("_run_date") or "")
            note = None
            if day != we:
                note = f"持股周末收盘价取自 {day} 收盘 manifest"
            return prices, note
    return {}, None


def _mss_from_manifest(record: dict[str, Any]) -> Optional[float]:
    payload = record.get("payload") or {}
    result = payload.get("result") or {}
    snap = result.get("snapshot") or {}
    if snap.get("mss_final") is not None:
        return float(snap["mss_final"])
    verify = result.get("verify") or {}
    if verify.get("mss_current") is not None:
        return float(verify["mss_current"])
    evaluation = result.get("evaluation") or {}
    report = evaluation.get("report") or {}
    if report.get("mss_final") is not None:
        return float(report["mss_final"])
    return None


def _manifest_sort_key(record: dict[str, Any]) -> str:
    path = record.get("_path") or ""
    if path:
        return path
    return str(record.get("at") or "")


def build_mss_trajectory(
    manifests: list[dict[str, Any]],
    week_start: date,
    week_end: date,
) -> list[dict[str, Any]]:
    """
    One MSS point per trading day (Mon–Fri): morning open + close EOD.

    Uses last close manifest per day; falls back to last intraday scan MSS.
    Avoids truncating to the last N raw manifests (which skews to the final day).
    """
    by_day: dict[str, list[dict[str, Any]]] = {}
    for record in manifests:
        day = str(record.get("_run_date") or "")
        if not day:
            continue
        mss = _mss_from_manifest(record)
        if mss is None:
            continue
        job = record.get("job")
        if job not in ("morning", "close", "intraday"):
            continue
        by_day.setdefault(day, []).append({**record, "_mss": mss})

    out: list[dict[str, Any]] = []
    d = week_start
    while d <= week_end:
        if d.weekday() >= 5:
            d += timedelta(days=1)
            continue
        ds = d.isoformat()
        rows = sorted(by_day.get(ds, []), key=_manifest_sort_key)
        morning_mss: Optional[float] = None
        close_mss: Optional[float] = None
        intraday_mss: Optional[float] = None
        for row in rows:
            job = row.get("job")
            mss = float(row["_mss"])
            if job == "morning" and morning_mss is None:
                morning_mss = mss
            elif job == "close":
                close_mss = mss
            elif job == "intraday":
                intraday_mss = mss
        eod = close_mss if close_mss is not None else intraday_mss
        if morning_mss is not None:
            out.append({"date": ds, "job": "morning", "mss_final": morning_mss})
        if eod is not None:
            out.append(
                {
                    "date": ds,
                    "job": "close" if close_mss is not None else "intraday",
                    "mss_final": eod,
                }
            )
        d += timedelta(days=1)
    return out


def _load_week_manifests(start: date, end: date) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for day, path in _iter_manifest_files(start, end):
        record = _load_manifest(path)
        if record:
            record["_run_date"] = day.isoformat()
            record["_path"] = str(path)
            records.append(record)
    return records


def _load_trade_ledger_range(start: date, end: date) -> list[dict[str, Any]]:
    path = default_ledger_path()
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        at = str(entry.get("at") or "")
        if not _date_in_range(at, start, end):
            continue
        entries.append(entry)
    return dedupe_trade_ledger_entries(entries)


def _holdings_shares_map(portfolio: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for h in portfolio.get("holdings") or []:
        code = _normalize_code(str(h.get("code", "")))
        if code:
            out[code] = int(h.get("shares") or 0)
    return out


def _holdings_shares_from_manifest(record: dict[str, Any]) -> dict[str, int]:
    snap, _ = _merged_enriched_from_manifest(record)
    if not snap:
        return {}
    return _holdings_shares_map(snap.get("portfolio") or {})


def _compute_trade_cash_flow(trades: list[dict[str, Any]]) -> float:
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


def _compute_realized_pnl(trades: list[dict[str, Any]]) -> float:
    """FIFO realized P&L on sell actions (buys alone do not count as loss)."""
    lots: dict[str, deque[tuple[int, float]]] = {}
    pnl = 0.0

    def _apply_buy(action: dict[str, Any]) -> None:
        shares = int(action.get("shares") or 0)
        amount = float(action.get("amount") or 0)
        commission = float(action.get("commission") or 0)
        if shares <= 0:
            return
        code = _normalize_code(str(action.get("code") or "__unknown__"))
        cost_per = (amount + commission) / shares
        lots.setdefault(code, deque()).append((shares, cost_per))

    def _apply_sell(action: dict[str, Any]) -> None:
        shares = int(action.get("shares") or 0)
        amount = float(action.get("amount") or 0)
        commission = float(action.get("commission") or 0)
        if shares <= 0:
            return
        code = _normalize_code(str(action.get("code") or "__unknown__"))
        proceeds_per = (amount - commission) / shares
        remaining = shares
        queue = lots.setdefault(code, deque())
        while remaining > 0 and queue:
            lot_shares, lot_cost = queue[0]
            take = min(remaining, lot_shares)
            pnl += take * (proceeds_per - lot_cost)
            remaining -= take
            if take >= lot_shares:
                queue.popleft()
            else:
                queue[0] = (lot_shares - take, lot_cost)
        if remaining > 0:
            fallback_cost = float(action.get("price") or 0)
            if fallback_cost > 0:
                pnl += remaining * (proceeds_per - fallback_cost)

    for entry in trades:
        actions = list(entry.get("actions") or [])
        if (
            actions
            and any(a.get("side") == "buy" for a in actions)
            and any(a.get("side") == "sell" for a in actions)
            and all(int(a.get("shares") or 0) <= 0 for a in actions)
        ):
            pnl += _compute_trade_cash_flow([entry])
            continue
        orphan_sells: list[dict[str, Any]] = []
        for action in actions:
            side = action.get("side")
            if side == "buy":
                _apply_buy(action)
            elif side == "sell":
                if int(action.get("shares") or 0) > 0:
                    orphan_sells.append(action)
                else:
                    amount = float(action.get("amount") or 0)
                    commission = float(action.get("commission") or 0)
                    pnl += amount - commission
        for action in orphan_sells:
            _apply_sell(action)

    return round(pnl, 2)


def _holding_pnl_rows(
    portfolio: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    week_start_prices: dict[str, float],
    week_end_prices: Optional[dict[str, float]] = None,
) -> list[dict[str, Any]]:
    end_prices = week_end_prices or {}
    rows: list[dict[str, Any]] = []
    for h in portfolio.get("holdings") or []:
        code = _normalize_code(str(h.get("code", "")))
        name = h.get("name") or code
        shares = int(h.get("shares") or 0)
        cost = float(h.get("cost") or 0)
        row = enriched.get(code, {})
        price = row.get("price") or h.get("price") or cost
        price = float(price)
        week_end = end_prices.get(code)
        week_end_price = float(week_end) if week_end else price
        mv = round(shares * week_end_price, 2)
        cost_basis = round(shares * cost, 2)
        unrealized = round(mv - cost_basis, 2)
        unrealized_pct = round(unrealized / cost_basis * 100, 2) if cost_basis else None
        week_start = week_start_prices.get(code)
        week_start_price = float(week_start) if week_start else None
        week_chg = None
        week_chg_pct = None
        if week_start_price and week_start_price > 0:
            week_chg = round((week_end_price - week_start_price) * shares, 2)
            week_chg_pct = round((week_end_price - week_start_price) / week_start_price * 100, 2)
        rows.append(
            {
                "code": code,
                "name": name,
                "shares": shares,
                "price": price,
                "week_end_price": week_end_price,
                "cost": cost,
                "market_value": mv,
                "unrealized_pnl": unrealized,
                "unrealized_pct": unrealized_pct,
                "week_start_price": week_start_price,
                "week_chg": week_chg,
                "week_chg_pct": week_chg_pct,
                "change_pct": row.get("change_pct"),
                "sector": row.get("sector") or row.get("industry") or h.get("sector") or h.get("industry"),
            }
        )
    rows.sort(key=lambda x: x.get("market_value") or 0, reverse=True)
    return rows


def _watchlist_rows(portfolio: dict[str, Any], enriched: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    held = {
        _normalize_code(str(h.get("code", "")))
        for h in portfolio.get("holdings") or []
        if _normalize_code(str(h.get("code", "")))
    }
    rows: list[dict[str, Any]] = []
    for w in portfolio.get("watchlist") or []:
        code = _normalize_code(str(w.get("code", "")))
        if not code or code in held:
            continue
        row = {**dict(w), **enriched.get(code, {})}
        rows.append(
            {
                "code": code,
                "name": row.get("name") or code,
                "price": row.get("price"),
                "change_pct": row.get("change_pct"),
                "sector": row.get("sector") or row.get("industry"),
                "reason": row.get("reason"),
                "source": row.get("source"),
            }
        )
    rows.sort(
        key=lambda x: float(x["change_pct"]) if x.get("change_pct") is not None else -999,
        reverse=True,
    )
    return rows


def _identify_hot_sectors(enriched: dict[str, dict[str, Any]], *, min_change: float = 1.0, limit: int = 8) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for code, row in enriched.items():
        chg = row.get("change_pct")
        if chg is None:
            continue
        chg_f = float(chg)
        if chg_f >= min_change:
            items.append(
                {
                    "code": code,
                    "name": row.get("name") or code,
                    "change_pct": chg_f,
                    "sector": row.get("sector") or row.get("industry") or "未分类",
                }
            )
    items.sort(key=lambda x: x["change_pct"], reverse=True)
    return items[:limit]


def _group_by_sector(enriched: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for code, row in enriched.items():
        sector = row.get("sector") or row.get("industry") or "综合"
        groups.setdefault(str(sector), []).append({**row, "code": code})
    for sector in groups:
        groups[sector].sort(
            key=lambda x: float(x.get("change_pct") or 0),
            reverse=True,
        )
    return dict(sorted(groups.items(), key=lambda kv: -max(float(x.get("change_pct") or 0) for x in kv[1])))


def build_sector_research_queries(sector_groups: dict[str, list[dict[str, Any]]], *, limit: int = 3) -> list[dict[str, str]]:
    queries: list[dict[str, str]] = []
    for sector, symbols in list(sector_groups.items())[:limit]:
        if sector == "综合":
            continue
        top = symbols[0] if symbols else {}
        label = f"{sector} 板块"
        names = " ".join(str(s.get("name") or s.get("code")) for s in symbols[:3])
        queries.append(
            {
                "type": "sector",
                "query": f"China A-share {sector} sector outlook weekly analysis 2026 {names}",
                "label": label,
            }
        )
    return queries


def run_sector_research(
    queries: list[dict[str, str]],
    settings: dict[str, Any],
) -> list[dict[str, Any]]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from agent_reach.daily_run.exa_client import ExaError, is_exa_available, summarize_hits, web_search_exa

    cfg = settings.get("weekly_report") or {}
    if cfg.get("exa_sector_research", True) is False:
        return []
    if not is_exa_available():
        return []

    plugin_cfg = settings.get("plugins") or {}
    timeout = int(plugin_cfg.get("exa_timeout", 45))
    max_q = int(cfg.get("max_sector_queries", 3))
    queries = queries[:max_q]
    if not queries:
        return []

    def _run_one(q: dict[str, str]) -> dict[str, Any]:
        try:
            hits = web_search_exa(q["query"], num_results=3, timeout=timeout)
            return {**q, "hits": hits, "summary": summarize_hits(hits), "success": True}
        except ExaError as exc:
            return {**q, "hits": [], "summary": str(exc), "success": False}

    workers = min(len(queries), 3)
    ordered: list[Optional[dict[str, Any]]] = [None] * len(queries)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_one, q): i for i, q in enumerate(queries)}
        for fut in as_completed(futures):
            ordered[futures[fut]] = fut.result()
    return [r for r in ordered if r is not None]


def _portfolio_has_positions(portfolio: dict[str, Any]) -> bool:
    return bool(portfolio.get("holdings") or portfolio.get("watchlist"))


def _portfolio_from_morning_baseline() -> Optional[dict[str, Any]]:
    from agent_reach.daily_run.workflows import load_morning_baseline

    try:
        baseline = load_morning_baseline()
    except FileNotFoundError:
        return None
    pf = dict(baseline.get("portfolio") or {})
    watchlist = baseline.get("watchlist") or pf.get("watchlist") or []
    if watchlist:
        pf["watchlist"] = [dict(w) for w in watchlist]
    if _portfolio_has_positions(pf):
        return pf
    return None


def _portfolio_from_manifests(
    manifests: list[dict[str, Any]],
    *,
    prefer_date: Optional[date] = None,
) -> Optional[dict[str, Any]]:
    """Recover holdings/watchlist from the latest snapshot embedded in run manifests."""

    def _from_snapshot(snap: dict[str, Any]) -> Optional[dict[str, Any]]:
        pf = dict(snap.get("portfolio") or {})
        watchlist = snap.get("watchlist") or pf.get("watchlist") or []
        if watchlist:
            pf["watchlist"] = [dict(w) for w in watchlist]
        if _portfolio_has_positions(pf):
            return pf
        return None

    if prefer_date is not None:
        ds = prefer_date.isoformat()
        day_rows = sorted(
            [m for m in manifests if m.get("_run_date") == ds],
            key=_manifest_sort_key,
        )
        for record in reversed(day_rows):
            snap = _snapshot_from_manifest(record)
            if snap:
                pf = _from_snapshot(snap)
                if pf:
                    return pf

    for record in sorted(manifests, key=_manifest_sort_key, reverse=True):
        snap = _snapshot_from_manifest(record)
        if snap:
            pf = _from_snapshot(snap)
            if pf:
                return pf
    return None


def resolve_weekly_portfolio(
    snapshot: dict[str, Any],
    portfolio: Optional[dict[str, Any]],
    manifests: list[dict[str, Any]],
    *,
    week_end: date,
) -> tuple[dict[str, Any], list[str]]:
    """Use portfolio.json when present; otherwise fall back to morning baseline or manifests."""
    pf = dict(portfolio or snapshot.get("portfolio") or {})
    if _portfolio_has_positions(pf):
        return pf, []

    notes: list[str] = []
    baseline_pf = _portfolio_from_morning_baseline()
    if baseline_pf:
        notes.append("持仓/观察池来自 last_morning.json（portfolio.json 为空或缺失）")
        return baseline_pf, notes

    manifest_pf = _portfolio_from_manifests(manifests, prefer_date=week_end)
    if manifest_pf:
        notes.append(f"持仓/观察池来自 {week_end.isoformat()} 运行 manifest（portfolio.json 为空）")
        return manifest_pf, notes

    manifest_pf = _portfolio_from_manifests(manifests)
    if manifest_pf:
        notes.append("持仓/观察池来自本周 manifest（portfolio.json 为空）")
        return manifest_pf, notes

    return pf, notes


def _load_experience_snippets(start: date, end: date, limit: int = 5) -> list[str]:
    from agent_reach.daily_run.experience import load_recent_experience

    recent = load_recent_experience(limit=50)
    snippets: list[str] = []
    for e in recent:
        ds = str(e.get("date") or "")
        if not _date_in_range(ds, start, end):
            continue
        hit = "✅" if e.get("prediction_hit") else "—"
        rules = "；".join((e.get("rules") or [])[:2])
        snippets.append(
            f"{ds} {e.get('name')} MSS={e.get('mss_final')} {hit} {rules}".strip()
        )
        if len(snippets) >= limit:
            break
    return snippets


def generate_weekly_report(
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    *,
    as_of: Optional[date] = None,
    portfolio: Optional[dict[str, Any]] = None,
) -> WeeklyReport:
    """Aggregate Mon–Fri manifests, ledger, portfolio into a weekly summary."""
    week_start, week_end = trading_week_range(as_of)
    manifests = _load_week_manifests(week_start, week_end)
    pf, pf_notes = resolve_weekly_portfolio(snapshot, portfolio, manifests, week_end=week_end)

    snap_for_symbols = snapshot
    if pf_notes:
        from agent_reach.daily_run.symbols import sync_snapshot_portfolio

        snap_for_symbols = dict(snapshot)
        sync_snapshot_portfolio(snap_for_symbols, pf)

    enriched = build_enriched_symbols(snap_for_symbols)
    trades = _load_trade_ledger_range(week_start, week_end)
    trade_cash_flow = _compute_trade_cash_flow(trades)
    realized = _compute_realized_pnl(trades)

    start_total: Optional[float] = None
    end_total: Optional[float] = None
    notes: list[str] = list(pf_notes)

    morning_totals: list[tuple[str, float]] = []
    close_totals: list[tuple[str, float]] = []
    for record in manifests:
        job = record.get("job")
        day = record.get("_run_date", "")
        total = _portfolio_total_from_manifest(record)
        if total is None:
            continue
        if job == "morning":
            morning_totals.append((day, total))
        elif job == "close":
            close_totals.append((day, total))

    mss_summary = build_mss_trajectory(manifests, week_start, week_end)

    if morning_totals:
        morning_totals.sort(key=lambda x: x[0])
        start_total = morning_totals[0][1]
    elif close_totals:
        close_totals.sort(key=lambda x: x[0])
        start_total = close_totals[0][1]
        notes.append("本周无早盘 manifest，周初净值取本周首个收盘 manifest")
    else:
        prior_close = _load_prior_close_total(week_start)
        if prior_close is not None:
            start_total = prior_close
            notes.append("本周 manifest 缺少周初净值，取上周最近收盘")

    if close_totals:
        close_totals.sort(key=lambda x: x[0])
        end_total = close_totals[-1][1]

    if end_total is None:
        end_total = _recalc_total_from_enriched(pf, enriched) or None

    if start_total is None:
        notes.append("缺少周初净值基线，无法计算周度组合盈亏")

    daily_totals: list[dict[str, Any]] = []
    for day, total in sorted(morning_totals, key=lambda x: x[0]):
        daily_totals.append({"date": day, "total": total, "job": "morning"})
    for day, total in sorted(close_totals, key=lambda x: x[0]):
        daily_totals.append({"date": day, "total": total, "job": "close"})

    cash_raw = pf.get("cash")
    cash = float(cash_raw) if cash_raw is not None else None
    ratio_raw = pf.get("cash_ratio")
    cash_ratio = float(ratio_raw) if ratio_raw is not None else None

    weekly_pnl: Optional[float] = None
    weekly_pnl_pct: Optional[float] = None
    if start_total is not None and end_total is not None:
        weekly_pnl = round(end_total - start_total, 2)
        if start_total:
            weekly_pnl_pct = round(weekly_pnl / start_total * 100, 2)

    start_cash: Optional[float] = None
    end_cash: Optional[float] = None
    start_stock_mv: Optional[float] = None
    end_stock_mv: Optional[float] = None
    stock_pnl: Optional[float] = None
    cash_pnl: Optional[float] = None

    start_record = _start_manifest_record(manifests, morning_totals, close_totals, week_start)
    end_record = _end_manifest_record(manifests, close_totals)
    if start_record:
        start_cash, start_stock_mv = _portfolio_parts_from_manifest(start_record)
    if end_record:
        end_cash, end_stock_mv = _portfolio_parts_from_manifest(end_record)
    elif cash is not None:
        end_cash = cash
        end_stock_mv = _stock_mv_from_enriched(pf, enriched)

    start_shares = (
        _holdings_shares_from_manifest(start_record)
        if start_record
        else _holdings_shares_map(pf)
    )
    end_shares = _holdings_shares_map(pf)
    holdings_changed = start_shares != end_shares

    manifest_cash_pnl: Optional[float] = None
    if start_cash is not None and end_cash is not None:
        manifest_cash_pnl = round(end_cash - start_cash, 2)

    if (
        not holdings_changed
        and manifest_cash_pnl is not None
        and abs(manifest_cash_pnl) < 0.01
    ):
        cash_pnl = 0.0
        if trades:
            notes.append("ledger 有成交记录但本周持仓/现金未变，盈亏分解不含成交流水")
    elif holdings_changed and trades and start_cash is not None:
        cash_pnl = trade_cash_flow
        end_cash = round(start_cash + cash_pnl, 2)
        notes.append("现金变动按 ledger 成交重算（本周持仓已变化）")
    elif manifest_cash_pnl is not None:
        cash_pnl = manifest_cash_pnl
    elif start_cash is not None and end_cash is not None:
        cash_pnl = round(end_cash - start_cash, 2)

    if weekly_pnl is not None and cash_pnl is not None:
        stock_pnl = round(weekly_pnl - cash_pnl, 2)
        if start_total is not None and start_cash is not None:
            start_stock_mv = round(start_total - start_cash, 2)
        if end_total is not None and end_cash is not None:
            end_stock_mv = round(end_total - end_cash, 2)
    elif start_stock_mv is not None and end_stock_mv is not None:
        stock_pnl = round(end_stock_mv - start_stock_mv, 2)

    week_start_prices, week_price_note = _week_start_prices_from_manifests(manifests, week_start)
    if week_price_note:
        notes.append(week_price_note)
    elif not week_start_prices and morning_totals:
        notes.append("本周无早盘报价 manifest，持股本周盈亏仅显示当日数据")

    week_end_prices, week_end_price_note = _week_end_prices_from_manifests(manifests, week_end)
    if week_end_price_note:
        notes.append(week_end_price_note)
    elif not week_end_prices:
        notes.append("本周无收盘 manifest，持股周末收盘价取当前报价")

    holdings = _holding_pnl_rows(pf, enriched, week_start_prices, week_end_prices)
    watchlist = _watchlist_rows(pf, enriched)
    hot_sectors = _identify_hot_sectors(enriched)
    sector_groups = _group_by_sector(enriched)
    experience_snippets = _load_experience_snippets(week_start, week_end)

    sector_queries = build_sector_research_queries(sector_groups)
    sector_research = run_sector_research(sector_queries, settings)

    from agent_reach.daily_run.weekly_insights import (
        generate_skill_learning,
        generate_weekly_improvements,
    )

    skill_items, skill_research = generate_skill_learning(
        settings=settings,
        hot_sectors=hot_sectors,
        holdings=holdings,
        experience_snippets=experience_snippets,
        manifests=manifests,
    )
    process_items = generate_weekly_improvements(
        settings=settings,
        week_start=week_start,
        week_end=week_end,
        manifests=manifests,
        weekly_pnl=weekly_pnl,
        weekly_pnl_pct=weekly_pnl_pct,
        holdings=holdings,
        watchlist=watchlist,
        trades=trades,
        mss_summary=mss_summary,
        experience_snippets=experience_snippets,
        hot_sectors=hot_sectors,
    )

    return WeeklyReport(
        week_start=week_start,
        week_end=week_end,
        start_total=start_total,
        end_total=end_total,
        weekly_pnl=weekly_pnl,
        weekly_pnl_pct=weekly_pnl_pct,
        realized_pnl=realized,
        trade_cash_flow=trade_cash_flow,
        start_cash=start_cash,
        end_cash=end_cash,
        start_stock_mv=start_stock_mv,
        end_stock_mv=end_stock_mv,
        stock_pnl=stock_pnl,
        cash_pnl=cash_pnl,
        holdings=holdings,
        watchlist=watchlist,
        hot_sectors=hot_sectors,
        sector_groups=sector_groups,
        trades=trades,
        mss_summary=mss_summary,
        experience_snippets=experience_snippets,
        sector_research=sector_research,
        skill_learning=[s.to_dict() for s in skill_items],
        skill_research=skill_research,
        process_improvements=[i.to_dict() for i in process_items],
        notes=notes,
        cash=cash,
        cash_ratio=cash_ratio,
        daily_totals=daily_totals,
    )


@dataclass
class WeeklySection:
    """One Feishu card body when split_push is enabled."""

    label: str
    markdown: str


def _join_section_lines(lines: list[str]) -> str:
    return "\n".join(lines).strip()


def _period_header_lines(report: WeeklyReport, *, continuation: bool = False) -> list[str]:
    ws, we = report.week_start.isoformat(), report.week_end.isoformat()
    if continuation:
        return [f"_📅 {ws} ~ {we}（续）_", ""]
    return [f"**📅 周期：** {ws} ~ {we}", ""]


def _summarize_week_trades(trades: list[dict[str, Any]], *, limit: int = 3) -> str:
    parts: list[str] = []
    for entry in trades[-limit:]:
        date_s = str(entry.get("at") or "")[:10]
        for action in entry.get("actions") or []:
            side = "买入" if action.get("side") == "buy" else "卖出"
            name = action.get("name") or action.get("code") or "?"
            shares = action.get("shares")
            price = action.get("price")
            if shares and price:
                parts.append(f"{date_s} {side}{name} {shares}股 @ ¥{float(price):.2f}")
            elif shares:
                parts.append(f"{date_s} {side}{name} {shares}股")
            else:
                amount = action.get("amount")
                if amount:
                    parts.append(f"{date_s} {side}{name} ¥{float(amount):,.0f}")
    return "；".join(parts)


def _weekly_report_data(report: WeeklyReport | dict[str, Any]) -> dict[str, Any]:
    if isinstance(report, WeeklyReport):
        return report.to_dict()
    return report


def build_weekly_pnl_attribution_lines(report: WeeklyReport | dict[str, Any]) -> list[str]:
    """Stock vs cash decomposition of weekly portfolio change."""
    data = _weekly_report_data(report)
    lines: list[str] = []

    stock_pnl = data.get("stock_pnl")
    cash_pnl = data.get("cash_pnl")
    start_stock_mv = data.get("start_stock_mv")
    end_stock_mv = data.get("end_stock_mv")
    start_cash = data.get("start_cash")
    end_cash = data.get("end_cash")

    if stock_pnl is None and cash_pnl is None:
        return lines

    parts: list[str] = []
    if stock_pnl is not None:
        sign = "+" if float(stock_pnl) >= 0 else ""
        parts.append(f"股票市值 {sign}¥{float(stock_pnl):,.2f}")
    if cash_pnl is not None:
        sign = "+" if float(cash_pnl) >= 0 else ""
        parts.append(f"持有现金 {sign}¥{float(cash_pnl):,.2f}")
    if parts:
        lines.append("- **盈亏分解：** " + " · ".join(parts))

    if start_stock_mv is not None and end_stock_mv is not None:
        stock_pct = None
        if float(start_stock_mv) > 0 and stock_pnl is not None:
            stock_pct = round(float(stock_pnl) / float(start_stock_mv) * 100, 2)
        pct_s = f"（{stock_pct:+.2f}%）" if stock_pct is not None else ""
        lines.append(
            f"- **股票市值：** ¥{float(start_stock_mv):,.2f} → ¥{float(end_stock_mv):,.2f}{pct_s}"
        )
    if start_cash is not None and end_cash is not None:
        cash_pct = None
        if float(start_cash) > 0 and cash_pnl is not None:
            cash_pct = round(float(cash_pnl) / float(start_cash) * 100, 2)
        pct_s = f"（{cash_pct:+.2f}%）" if cash_pct is not None else ""
        lines.append(
            f"- **持有现金：** ¥{float(start_cash):,.2f} → ¥{float(end_cash):,.2f}{pct_s}"
        )

    return lines


def build_weekly_pnl_explanation(report: WeeklyReport | dict[str, Any]) -> list[str]:
    """Narrative breakdown of weekly P&L for Saturday review cards and skill writeback."""
    data = _weekly_report_data(report)
    lines: list[str] = []

    pnl = data.get("weekly_pnl")
    pct = data.get("weekly_pnl_pct")
    holdings = data.get("holdings") or []
    trades = data.get("trades") or []
    realized = float(data.get("realized_pnl") or 0)
    trade_cash_flow = float(data.get("trade_cash_flow") if data.get("trade_cash_flow") is not None else realized)
    notes = data.get("notes") or []
    daily_totals = data.get("daily_totals") or []

    if pnl is None:
        lines.append("- **情况说明：** 缺少完整净值轨迹，以下以当前持仓与 ledger 估算。")
    else:
        pnl_f = float(pnl)
        pct_f = float(pct) if pct is not None else 0.0
        if pnl_f > 0 and pct_f >= 1:
            verdict = f"本周组合盈利 **{pct_f:+.1f}%**（+¥{pnl_f:,.2f}）"
        elif pnl_f < 0 and pct_f <= -1:
            verdict = f"本周组合回撤 **{pct_f:.1f}%**（¥{pnl_f:,.2f}）"
        else:
            verdict = f"本周组合净值基本 **持平**（{pnl_f:+,.2f} 元，{pct_f:+.1f}%）"
        lines.append(f"- **情况说明：** {verdict}。")

    lines.extend(build_weekly_pnl_attribution_lines(data))

    close_totals = sorted(
        [row for row in daily_totals if row.get("job") == "close" and row.get("total") is not None],
        key=lambda x: str(x.get("date") or ""),
    )
    if len(close_totals) >= 2:
        first, last = close_totals[0], close_totals[-1]
        lines.append(
            "- **收盘净值轨迹：** "
            f"{first['date']} ¥{float(first['total']):,.2f} → "
            f"{last['date']} ¥{float(last['total']):,.2f}"
        )
    elif close_totals:
        row = close_totals[-1]
        lines.append(f"- **最近收盘净值：** {row['date']} ¥{float(row['total']):,.2f}")

    if holdings:
        total_unrealized = sum(float(h.get("unrealized_pnl") or 0) for h in holdings)
        lines.append(f"- **持仓浮盈合计：** ¥{total_unrealized:+,.0f}（{len(holdings)} 只）")
        week_rows = [h for h in holdings if h.get("week_chg") is not None]
        if week_rows:
            week_chg_total = sum(float(h["week_chg"]) for h in week_rows)
            lines.append(
                "- **持股周度市值变动：** "
                f"¥{week_chg_total:+,.2f}（按周初价估算，不含新开仓成本口径）"
            )
            top = sorted(week_rows, key=lambda x: abs(float(x["week_chg"])), reverse=True)[:3]
            contrib = "、".join(
                f"{h.get('name') or h.get('code')} {float(h['week_chg']):+,.0f}元" for h in top
            )
            lines.append(f"- **周内贡献前列：** {contrib}")

    cash = data.get("cash")
    cash_ratio = data.get("cash_ratio")
    if cash is not None and cash_ratio is not None:
        lines.append(f"- **现金仓位：** {float(cash_ratio):.1%}（¥{float(cash):,.0f}）")

    if trades:
        sign = "+" if trade_cash_flow >= 0 else ""
        lines.append(
            f"- **成交现金流（ledger，去重后）：** {sign}¥{trade_cash_flow:,.2f}，共 {len(trades)} 笔"
        )
        if abs(realized) > 0.01:
            rsign = "+" if realized >= 0 else ""
            lines.append(f"- **已实现盈亏（FIFO）：** {rsign}¥{realized:,.2f}")
        trade_summary = _summarize_week_trades(trades)
        if trade_summary:
            lines.append(f"  - {trade_summary}")

    if (
        pnl is not None
        and abs(float(pnl)) < 1
        and trades
        and abs(trade_cash_flow) > 1000
    ):
        lines.append(
            "- _净值变动接近 0 但 ledger 有大额成交：可能缺少周初净值基线，"
            "或买入使用既有现金、市值波动与成交相互抵消。_"
        )

    for note in notes:
        if "无早盘 manifest" in note or "周初净值" in note or "缺少周初" in note:
            lines.append(f"- _{note}_")
            break

    return lines


def _render_pnl_lines(report: WeeklyReport) -> list[str]:
    lines = ["## 💰 本周盈亏"]
    if report.weekly_pnl is not None:
        sign = "+" if report.weekly_pnl >= 0 else ""
        pct = ""
        if report.weekly_pnl_pct is not None:
            pct = f"（{sign}{report.weekly_pnl_pct}%）"
        lines.append(f"- **组合净值变动：** {sign}¥{report.weekly_pnl:,.2f}{pct}")
        if report.start_total is not None and report.end_total is not None:
            lines.append(f"- 周初 ¥{report.start_total:,.2f} → 周末 ¥{report.end_total:,.2f}")
    else:
        lines.append("- 暂无完整净值数据（需本周 daily-run manifest）")
    if report.trades and abs(report.trade_cash_flow) > 0.01:
        sign = "+" if report.trade_cash_flow >= 0 else ""
        lines.append(f"- **本周成交现金流（ledger，去重后）：** {sign}¥{report.trade_cash_flow:,.2f}")
    if report.realized_pnl and abs(report.realized_pnl) > 0.01:
        sign = "+" if report.realized_pnl >= 0 else ""
        lines.append(f"- **本周已实现盈亏（FIFO）：** {sign}¥{report.realized_pnl:,.2f}")
    if report.trades:
        lines.append(f"- 成交笔数：**{len(report.trades)}**")
    lines.extend(build_weekly_pnl_explanation(report))
    for note in report.notes:
        if not any(note in line for line in lines):
            lines.append(f"- _{note}_")
    lines.append("")
    return lines


def _render_holdings_lines(report: WeeklyReport) -> list[str]:
    lines = ["## 📊 持股（本周盈亏）"]
    if report.holdings:
        rows = sorted(
            report.holdings,
            key=lambda h: abs(float(h.get("week_chg") or 0)),
            reverse=True,
        )
        for h in rows:
            week_s = ""
            if h.get("week_chg") is not None:
                wc = float(h["week_chg"])
                pct = h.get("week_chg_pct")
                pct_s = f"（{float(pct):+.2f}%）" if pct is not None else ""
                week_s = f" **本周盈亏 ¥{wc:+,.0f}{pct_s}**"
            chg = h.get("change_pct")
            chg_s = f" · 今日 {float(chg):+.2f}%" if chg is not None else ""
            end_px = float(h.get("week_end_price") or h.get("price") or 0)
            price_s = f" · 周末收盘 ¥{end_px:.2f}"
            start_s = ""
            if h.get("week_start_price") is not None:
                start_s = f" · 周初 ¥{float(h['week_start_price']):.2f}"
            lines.append(
                f"- **{h['name']}** ({h['code']}) {h['shares']}股 "
                f"市值 ¥{h['market_value']:,.0f}{price_s}{start_s}{week_s}{chg_s}"
            )
    else:
        lines.append("- 当前无持仓")
    lines.append("")
    return lines


def _render_watchlist_lines(report: WeeklyReport) -> list[str]:
    lines = ["## 👀 观察池"]
    if report.watchlist:
        for w in report.watchlist:
            chg = w.get("change_pct")
            chg_s = f" {float(chg):+.2f}%" if chg is not None else ""
            price_s = f"¥{float(w['price']):.2f} " if w.get("price") else ""
            lines.append(f"- **{w['name']}** ({w['code']}) {price_s}{chg_s}")
    else:
        lines.append("- 观察池为空或标的已在持仓中")
    lines.append("")
    return lines


def _render_market_lines(report: WeeklyReport) -> list[str]:
    lines = ["## 🔥 热门板块 / 强势标的"]
    if report.hot_sectors:
        for item in report.hot_sectors:
            lines.append(
                f"- **{item['name']}** ({item['code']}) {item['change_pct']:+.2f}% · {item['sector']}"
            )
    else:
        lines.append("- 本周暂无涨幅 >1% 的持仓/观察标的")
    lines.append("")

    lines.append("## 🏭 板块分析")
    if report.sector_groups:
        for sector, symbols in list(report.sector_groups.items())[:6]:
            parts = []
            for s in symbols[:4]:
                name = s.get("name") or s.get("code")
                chg = s.get("change_pct")
                if chg is not None:
                    parts.append(f"{name} {float(chg):+.1f}%")
                else:
                    parts.append(str(name))
            lines.append(f"- **{sector}：** " + "、".join(parts))
    else:
        lines.append("- 无板块分组数据")
    lines.append("")

    if report.sector_research:
        lines.append("### 板块深度（Exa）")
        for r in report.sector_research:
            status = "✅" if r.get("success") else "⚠️"
            lines.append(f"**{status} {r.get('label', '板块')}**")
            if r.get("summary"):
                lines.append(r["summary"])
            lines.append("")
    return lines


def _render_mss_lines(report: WeeklyReport) -> list[str]:
    if not report.mss_summary:
        return []
    lines = ["## 📈 MSS 本周轨迹"]
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    by_date: dict[str, dict[str, float]] = {}
    for row in report.mss_summary:
        ds = row["date"]
        by_date.setdefault(ds, {})[row["job"]] = float(row["mss_final"])
    for ds in sorted(by_date.keys()):
        slots = by_date[ds]
        wd = weekday_cn[date.fromisoformat(ds).weekday()]
        short = ds[5:]
        parts: list[str] = []
        if "morning" in slots:
            parts.append(f"早 {slots['morning']:.1f}")
        if "close" in slots:
            parts.append(f"收 {slots['close']:.1f}")
        elif "intraday" in slots:
            parts.append(f"盘 {slots['intraday']:.1f}")
        if parts:
            lines.append(f"- **{short} {wd}** " + " → ".join(parts))
    lines.append("")
    return lines


def _render_experience_lines(report: WeeklyReport) -> list[str]:
    if not report.experience_snippets:
        return []
    lines = ["## 📚 本周经验"]
    for s in report.experience_snippets:
        lines.append(f"- {s}")
    lines.append("")
    return lines


def _render_insights_lines(report: WeeklyReport) -> list[str]:
    from agent_reach.daily_run.weekly_insights import (
        InsightItem,
        SkillLearningItem,
        render_improvements_markdown,
        render_skill_learning_markdown,
    )

    lines: list[str] = []
    skill_md = render_skill_learning_markdown(
        [SkillLearningItem(**s) for s in report.skill_learning],
        report.skill_research,
    )
    if skill_md:
        lines.extend(skill_md.splitlines())
        lines.append("")

    imp_md = render_improvements_markdown(
        [InsightItem(**i) for i in report.process_improvements]
    )
    if imp_md:
        lines.extend(imp_md.splitlines())
    return lines


def render_weekly_sections(report: WeeklyReport) -> list[WeeklySection]:
    """Split weekly report into Feishu-friendly sections (one card each)."""
    sections: list[WeeklySection] = []

    portfolio_lines = (
        _period_header_lines(report)
        + _render_pnl_lines(report)
        + _render_holdings_lines(report)
        + _render_watchlist_lines(report)
    )
    sections.append(WeeklySection("盈亏·持仓", _join_section_lines(portfolio_lines)))

    market_lines = _period_header_lines(report, continuation=True) + _render_market_lines(report)
    wl_update = report.watchlist_candidates_update or {}
    if wl_update.get("candidates") or wl_update.get("message"):
        from agent_reach.daily_run.watchlist_candidates import render_weekly_candidates_markdown

        market_lines.append("")
        market_lines.append(render_weekly_candidates_markdown(wl_update))
    sections.append(WeeklySection("板块·热点", _join_section_lines(market_lines)))

    track_body = _render_mss_lines(report) + _render_experience_lines(report)
    if track_body:
        track_lines = _period_header_lines(report, continuation=True) + track_body
        sections.append(WeeklySection("MSS·经验", _join_section_lines(track_lines)))

    insight_body = _render_insights_lines(report)
    if insight_body:
        insight_lines = _period_header_lines(report, continuation=True) + insight_body
        sections.append(WeeklySection("学习·改进", _join_section_lines(insight_lines)))

    return sections


def render_weekly_markdown(report: WeeklyReport) -> str:
    """Render full weekly summary markdown (all sections joined)."""
    parts = [s.markdown for s in render_weekly_sections(report) if s.markdown]
    return "\n\n".join(parts).strip()


def weekly_section_title(
    report: WeeklyReport,
    index: int,
    total: int,
    label: str,
) -> str:
    range_part = f"{report.week_start:%m/%d}–{report.week_end:%m/%d}"
    title = f"📋 周报 {index}/{total} · {label} · {range_part}"
    if index == 1 and report.weekly_pnl is not None:
        sign = "+" if report.weekly_pnl >= 0 else ""
        title += f" · {sign}¥{report.weekly_pnl:,.0f}"
    return title


def weekly_report_title(report: WeeklyReport) -> str:
    pnl_part = ""
    if report.weekly_pnl is not None:
        sign = "+" if report.weekly_pnl >= 0 else ""
        pnl_part = f" · {sign}¥{report.weekly_pnl:,.0f}"
    return f"📋 周报总结 · {report.week_start:%m/%d}–{report.week_end:%m/%d}{pnl_part}"

# -*- coding: utf-8
"""Weekly trading summary — PnL, holdings, watchlist, hot sectors, sector analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.portfolio_manager import default_ledger_path
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


def _portfolio_total_from_manifest(record: dict[str, Any]) -> Optional[float]:
    payload = record.get("payload") or {}
    for key in ("result",):
        block = payload.get(key) or {}
        snap = block.get("snapshot") or {}
        pf = snap.get("portfolio") or {}
        total = pf.get("total")
        if total is not None:
            return float(total)
    return None


def _snapshot_from_manifest(record: dict[str, Any]) -> Optional[dict[str, Any]]:
    payload = record.get("payload") or {}
    result = payload.get("result") or {}
    snap = result.get("snapshot")
    if isinstance(snap, dict):
        return snap
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


def _week_start_prices_from_manifests(
    manifests: list[dict[str, Any]],
    week_start: date,
) -> dict[str, float]:
    """First morning snapshot prices on/after week_start (Mon open baseline)."""
    morning = sorted(
        [m for m in manifests if m.get("job") == "morning"],
        key=lambda m: str(m.get("_run_date") or ""),
    )
    ws = week_start.isoformat()
    for record in morning:
        day = str(record.get("_run_date") or "")
        if day and day >= ws:
            snap = _snapshot_from_manifest(record)
            if snap:
                prices = _prices_from_snapshot(snap)
                if prices:
                    return prices
    if morning:
        snap = _snapshot_from_manifest(morning[0])
        if snap:
            return _prices_from_snapshot(snap)
    return {}


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
    return entries


def _compute_realized_pnl(trades: list[dict[str, Any]]) -> float:
    """Approximate realized PnL from ledger buy/sell actions (sell proceeds − buy cost)."""
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


def _holding_pnl_rows(
    portfolio: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    week_start_prices: dict[str, float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for h in portfolio.get("holdings") or []:
        code = _normalize_code(str(h.get("code", "")))
        name = h.get("name") or code
        shares = int(h.get("shares") or 0)
        cost = float(h.get("cost") or 0)
        row = enriched.get(code, {})
        price = row.get("price") or h.get("price") or cost
        price = float(price)
        mv = round(shares * price, 2)
        cost_basis = round(shares * cost, 2)
        unrealized = round(mv - cost_basis, 2)
        unrealized_pct = round(unrealized / cost_basis * 100, 2) if cost_basis else None
        week_start = week_start_prices.get(code)
        week_chg = None
        week_chg_pct = None
        if week_start and week_start > 0:
            week_chg = round((price - week_start) * shares, 2)
            week_chg_pct = round((price - week_start) / week_start * 100, 2)
        rows.append(
            {
                "code": code,
                "name": name,
                "shares": shares,
                "price": price,
                "cost": cost,
                "market_value": mv,
                "unrealized_pnl": unrealized,
                "unrealized_pct": unrealized_pct,
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
        if job == "morning" and total is not None:
            morning_totals.append((day, total))
        if job == "close" and total is not None:
            close_totals.append((day, total))

    mss_summary = build_mss_trajectory(manifests, week_start, week_end)

    if morning_totals:
        morning_totals.sort(key=lambda x: x[0])
        start_total = morning_totals[0][1]
    if close_totals:
        close_totals.sort(key=lambda x: x[0])
        end_total = close_totals[-1][1]

    if end_total is None:
        end_total = float(pf.get("total") or 0) or None
    if start_total is None and end_total is not None:
        start_total = end_total
        notes.append("本周无早盘 manifest，周初净值用周末/当前估值代替")

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

    week_start_prices = _week_start_prices_from_manifests(manifests, week_start)
    if not week_start_prices and morning_totals:
        notes.append("本周无早盘报价 manifest，持股周涨跌仅显示当日数据")

    holdings = _holding_pnl_rows(pf, enriched, week_start_prices)
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


def build_weekly_pnl_explanation(report: WeeklyReport | dict[str, Any]) -> list[str]:
    """Narrative breakdown of weekly P&L for Saturday review cards and skill writeback."""
    data = _weekly_report_data(report)
    lines: list[str] = []

    pnl = data.get("weekly_pnl")
    pct = data.get("weekly_pnl_pct")
    holdings = data.get("holdings") or []
    trades = data.get("trades") or []
    realized = float(data.get("realized_pnl") or 0)
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
        sign = "+" if realized >= 0 else ""
        lines.append(
            f"- **成交现金流（ledger）：** {sign}¥{realized:,.2f}，共 {len(trades)} 笔"
        )
        trade_summary = _summarize_week_trades(trades)
        if trade_summary:
            lines.append(f"  - {trade_summary}")

    if pnl is not None and abs(float(pnl)) < 1 and trades and abs(realized) > 1000:
        lines.append(
            "- _净值变动接近 0 但 ledger 有大额成交：可能缺少周初早盘净值基线，"
            "或买入使用既有现金、市值波动与成交相互抵消。_"
        )

    for note in notes:
        if "无早盘 manifest" in note or "周初净值" in note:
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
    if report.realized_pnl:
        sign = "+" if report.realized_pnl >= 0 else ""
        lines.append(f"- **本周成交净额（ledger）：** {sign}¥{report.realized_pnl:,.2f}")
    if report.trades:
        lines.append(f"- 成交笔数：**{len(report.trades)}**")
    lines.extend(build_weekly_pnl_explanation(report))
    for note in report.notes:
        if not any(note in line for line in lines):
            lines.append(f"- _{note}_")
    lines.append("")
    return lines


def _render_holdings_lines(report: WeeklyReport) -> list[str]:
    lines = ["## 📊 持股"]
    if report.holdings:
        for h in report.holdings:
            chg = h.get("change_pct")
            chg_s = f" 今日 {float(chg):+.2f}%" if chg is not None else ""
            upnl = h.get("unrealized_pnl")
            upnl_s = f" 浮盈 ¥{upnl:+,.0f}" if upnl is not None else ""
            week_s = ""
            if h.get("week_chg_pct") is not None:
                week_s = f" 本周 {h['week_chg_pct']:+.2f}%"
            lines.append(
                f"- **{h['name']}** ({h['code']}) {h['shares']}股 "
                f"@ ¥{h['price']:.2f} 市值 ¥{h['market_value']:,.0f}{upnl_s}{chg_s}{week_s}"
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

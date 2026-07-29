# -*- coding: utf-8
"""Daily P&L, holdings distribution, and cash summary for close review."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from agent_reach.daily_run.symbols import build_enriched_symbols, portfolio_from_snapshot
from agent_reach.daily_run.trade_calendar import today_shanghai
from agent_reach.daily_run.weekly_report import (
    _compute_realized_pnl,
    _holding_pnl_rows,
    _load_trade_ledger_range,
    _prices_from_snapshot,
    _watchlist_rows,
)


@dataclass
class ClosePortfolioSummary:
    as_of: str
    start_total: Optional[float]
    end_total: Optional[float]
    daily_pnl: Optional[float]
    daily_pnl_pct: Optional[float]
    cash: Optional[float]
    cash_ratio: Optional[float]
    holdings: list[dict[str, Any]] = field(default_factory=list)
    watchlist: list[dict[str, Any]] = field(default_factory=list)
    sector_weights: list[dict[str, Any]] = field(default_factory=list)
    realized_pnl: float = 0.0
    trades: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "start_total": self.start_total,
            "end_total": self.end_total,
            "daily_pnl": self.daily_pnl,
            "daily_pnl_pct": self.daily_pnl_pct,
            "cash": self.cash,
            "cash_ratio": self.cash_ratio,
            "holdings": self.holdings,
            "watchlist": self.watchlist,
            "sector_weights": self.sector_weights,
            "realized_pnl": self.realized_pnl,
            "trades": self.trades,
            "notes": self.notes,
        }


def _recalc_portfolio_totals(portfolio: dict[str, Any], enriched: dict[str, dict[str, Any]]) -> None:
    from agent_reach.daily_run.portfolio_manager import _recalc_totals

    _recalc_totals(portfolio, enriched)


def _sector_weights(holdings: list[dict[str, Any]], end_total: Optional[float]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for h in holdings:
        sector = str(h.get("sector") or "未分类")
        bucket = groups.setdefault(
            sector,
            {"sector": sector, "market_value": 0.0, "weight_pct": 0.0, "names": []},
        )
        mv = float(h.get("market_value") or 0)
        bucket["market_value"] += mv
        name = h.get("name") or h.get("code")
        if name and name not in bucket["names"]:
            bucket["names"].append(str(name))
    rows = list(groups.values())
    rows.sort(key=lambda x: x["market_value"], reverse=True)
    denom = float(end_total) if end_total and end_total > 0 else sum(r["market_value"] for r in rows)
    for row in rows:
        row["market_value"] = round(row["market_value"], 2)
        row["weight_pct"] = round(row["market_value"] / denom * 100, 1) if denom > 0 else 0.0
    return rows


def _attach_weights(holdings: list[dict[str, Any]], end_total: Optional[float]) -> list[dict[str, Any]]:
    denom = float(end_total) if end_total and end_total > 0 else sum(float(h.get("market_value") or 0) for h in holdings)
    out: list[dict[str, Any]] = []
    for h in holdings:
        row = dict(h)
        mv = float(row.get("market_value") or 0)
        row["weight_pct"] = round(mv / denom * 100, 1) if denom > 0 else None
        out.append(row)
    return out


def build_close_portfolio_summary(
    current: dict[str, Any],
    baseline: dict[str, Any],
    *,
    trades: Optional[list[dict[str, Any]]] = None,
    as_of: Optional[date] = None,
) -> ClosePortfolioSummary:
    """Build end-of-day portfolio summary from close snapshot vs morning baseline."""
    day = as_of or today_shanghai()
    enriched = build_enriched_symbols(current)
    close_pf = portfolio_from_snapshot(current)
    _recalc_portfolio_totals(close_pf, enriched)

    morning_pf = dict(baseline.get("portfolio") or {})
    morning_prices = _prices_from_snapshot(baseline)
    start_total = morning_pf.get("total")
    if start_total is not None:
        start_total = float(start_total)

    end_total = close_pf.get("total")
    if end_total is not None:
        end_total = float(end_total)

    notes: list[str] = []
    daily_pnl: Optional[float] = None
    daily_pnl_pct: Optional[float] = None
    if start_total is not None and end_total is not None:
        daily_pnl = round(end_total - start_total, 2)
        daily_pnl_pct = round(daily_pnl / start_total * 100, 2) if start_total > 0 else None
    elif end_total is not None:
        notes.append("缺少早盘净值基线，无法计算当日组合盈亏")

    holdings = _holding_pnl_rows(close_pf, enriched, morning_prices)
    holdings = _attach_weights(holdings, end_total)
    watchlist = _watchlist_rows(close_pf, enriched)
    sector_weights = _sector_weights(holdings, end_total)

    ledger_trades = _load_trade_ledger_range(day, day)
    realized = _compute_realized_pnl(ledger_trades)

    cash = close_pf.get("cash")
    cash_ratio = close_pf.get("cash_ratio")
    if cash is not None:
        cash = float(cash)
    if cash_ratio is not None:
        cash_ratio = float(cash_ratio)

    return ClosePortfolioSummary(
        as_of=day.isoformat(),
        start_total=start_total,
        end_total=end_total,
        daily_pnl=daily_pnl,
        daily_pnl_pct=daily_pnl_pct,
        cash=cash,
        cash_ratio=cash_ratio,
        holdings=holdings,
        watchlist=watchlist,
        sector_weights=sector_weights,
        realized_pnl=realized,
        trades=ledger_trades or list(trades or []),
        notes=notes,
    )


def build_daily_pnl_explanation(summary: ClosePortfolioSummary | dict[str, Any]) -> list[str]:
    """Narrative breakdown of daily P&L for close review cards."""
    data = summary.to_dict() if isinstance(summary, ClosePortfolioSummary) else summary
    lines: list[str] = []

    pnl = data.get("daily_pnl")
    pct = data.get("daily_pnl_pct")
    holdings = data.get("holdings") or []
    realized = float(data.get("realized_pnl") or 0)
    trades = data.get("trades") or []
    notes = data.get("notes") or []

    if pnl is None:
        if notes:
            lines.append(f"- **情况说明：** {notes[0]}")
        else:
            lines.append("- **情况说明：** 缺少完整净值轨迹，以下以当前持仓估算。")
    else:
        pnl_f = float(pnl)
        pct_f = float(pct) if pct is not None else 0.0
        if pnl_f > 0 and pct_f >= 0.3:
            verdict = f"今日组合盈利 **{pct_f:+.2f}%**（+¥{pnl_f:,.2f}）"
        elif pnl_f < 0 and pct_f <= -0.3:
            verdict = f"今日组合回撤 **{pct_f:.2f}%**（¥{pnl_f:,.2f}）"
        else:
            verdict = f"今日组合净值基本 **持平**（{pnl_f:+,.2f} 元，{pct_f:+.2f}%）"
        lines.append(f"- **情况说明：** {verdict}。")

    if holdings:
        day_rows = [h for h in holdings if h.get("week_chg") is not None]
        if day_rows:
            day_chg_total = sum(float(h["week_chg"]) for h in day_rows)
            lines.append(
                "- **持股日内市值变动：** "
                f"¥{day_chg_total:+,.2f}（按早盘价估算，不含新开仓成本口径）"
            )
            top = sorted(day_rows, key=lambda x: abs(float(x["week_chg"])), reverse=True)[:3]
            contrib = "、".join(
                f"{h.get('name') or h.get('code')} {float(h['week_chg']):+,.0f}元" for h in top
            )
            lines.append(f"- **日内贡献前列：** {contrib}")

        losers = [h for h in day_rows if float(h.get("week_chg") or 0) < 0]
        winners = [h for h in day_rows if float(h.get("week_chg") or 0) > 0]
        if losers and winners:
            worst = min(losers, key=lambda x: float(x["week_chg"]))
            best = max(winners, key=lambda x: float(x["week_chg"]))
            lines.append(
                "- **涨跌分化：** "
                f"拖累 {worst.get('name')} {float(worst['week_chg']):+,.0f}元；"
                f"支撑 {best.get('name')} {float(best['week_chg']):+,.0f}元"
            )

    cash = data.get("cash")
    cash_ratio = data.get("cash_ratio")
    if cash is not None and cash_ratio is not None:
        deployable_note = ""
        if float(cash_ratio) >= 0.5:
            deployable_note = "，现金偏高、仓位偏轻"
        elif float(cash_ratio) <= 0.2:
            deployable_note = "，现金偏低、仓位偏重"
        lines.append(
            f"- **现金影响：** 收盘现金 {float(cash_ratio):.1%}（¥{float(cash):,.0f}）{deployable_note}"
        )

    if trades and abs(realized) > 0.01:
        sign = "+" if realized >= 0 else ""
        lines.append(
            f"- **成交现金流（ledger）：** {sign}¥{realized:,.2f}，共 {len(trades)} 笔"
        )

    if pnl is not None and trades and abs(float(pnl)) < 1 and abs(realized) > 500:
        lines.append(
            "- _净值变动接近 0 但 ledger 有大额成交：可能买入使用既有现金，"
            "或市值波动与成交相互抵消。_"
        )

    for note in notes[1:]:
        lines.append(f"- _{note}_")

    return lines


def render_close_portfolio_markdown(summary: ClosePortfolioSummary | dict[str, Any]) -> str:
    data = summary.to_dict() if isinstance(summary, ClosePortfolioSummary) else summary
    lines: list[str] = ["## 💰 当日盈亏"]

    if data.get("daily_pnl") is not None:
        pnl = float(data["daily_pnl"])
        sign = "+" if pnl >= 0 else ""
        pct_s = ""
        if data.get("daily_pnl_pct") is not None:
            pct = float(data["daily_pnl_pct"])
            pct_s = f"（{sign}{pct}%）"
        lines.append(f"- **组合净值变动：** {sign}¥{pnl:,.2f}{pct_s}")
        if data.get("start_total") is not None and data.get("end_total") is not None:
            lines.append(
                f"- 早盘 ¥{float(data['start_total']):,.2f} → 收盘 ¥{float(data['end_total']):,.2f}"
            )
    else:
        if data.get("end_total") is not None:
            lines.append(f"- **收盘净值：** ¥{float(data['end_total']):,.2f}")
        else:
            lines.append("- 暂无完整净值数据（需早盘基线 + 收盘 snapshot）")

    if data.get("realized_pnl"):
        realized = float(data["realized_pnl"])
        sign = "+" if realized >= 0 else ""
        lines.append(f"- **今日成交净额（ledger）：** {sign}¥{realized:,.2f}")

    lines.append("")
    lines.append("## 📊 持仓分布")
    holdings = data.get("holdings") or []
    if holdings:
        for h in holdings:
            chg = h.get("change_pct")
            chg_s = f" 今日 {float(chg):+.2f}%" if chg is not None else ""
            day_s = ""
            if h.get("week_chg") is not None:
                day_s = f" 日内 {float(h['week_chg']):+,.0f}元"
            upnl = h.get("unrealized_pnl")
            upnl_s = f" 浮盈 ¥{upnl:+,.0f}" if upnl is not None else ""
            weight = h.get("weight_pct")
            weight_s = f" 权重 {weight:.1f}%" if weight is not None else ""
            lines.append(
                f"- **{h['name']}** ({h['code']}) {h['shares']}股 "
                f"@ ¥{h['price']:.2f} 市值 ¥{h['market_value']:,.0f}{weight_s}{upnl_s}{chg_s}{day_s}"
            )
    else:
        lines.append("- 当前无持仓")

    sector_weights = data.get("sector_weights") or []
    if sector_weights:
        lines.append("")
        lines.append("## 🏭 行业分布")
        for row in sector_weights[:6]:
            names = "、".join(row.get("names") or [])[:40]
            suffix = f" · {names}" if names else ""
            lines.append(
                f"- **{row['sector']}** {row['weight_pct']:.1f}%"
                f"（¥{row['market_value']:,.0f}）{suffix}"
            )

    lines.append("")
    lines.append("## 💵 现金")
    cash = data.get("cash")
    cash_ratio = data.get("cash_ratio")
    if cash is not None and cash_ratio is not None:
        lines.append(f"- **现金：** ¥{float(cash):,.2f}（{float(cash_ratio):.1%}）")
        if data.get("end_total") is not None:
            mv = float(data["end_total"]) - float(cash)
            lines.append(f"- **股票市值：** ¥{mv:,.2f}（{1 - float(cash_ratio):.1%}）")
    elif cash is not None:
        lines.append(f"- **现金：** ¥{float(cash):,.2f}")
    else:
        lines.append("- 暂无现金数据")

    watchlist = data.get("watchlist") or []
    if watchlist:
        lines.append("")
        lines.append("## 👀 观察池")
        for w in watchlist:
            chg = w.get("change_pct")
            chg_s = f" {float(chg):+.2f}%" if chg is not None else ""
            price_s = f"¥{float(w['price']):.2f} " if w.get("price") else ""
            lines.append(f"- **{w['name']}** ({w['code']}) {price_s}{chg_s}")

    lines.append("")
    lines.append("## 📝 盈亏归因")
    lines.extend(build_daily_pnl_explanation(data))

    return "\n".join(lines).strip()

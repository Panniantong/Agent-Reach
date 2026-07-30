# -*- coding: utf-8
"""Daily P&L, holdings distribution, and cash summary for close review."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from agent_reach.daily_run.snapshot_builder import _normalize_code
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
    cash_delta: Optional[float] = None
    stock_mv: Optional[float] = None
    stock_ratio: Optional[float] = None
    holdings_count: int = 0
    watchlist_count: int = 0
    max_weight_pct: Optional[float] = None
    winners: int = 0
    losers: int = 0
    flat: int = 0
    day_mv_change: Optional[float] = None
    total_unrealized: Optional[float] = None
    position_change: str = "无调仓"
    holdings: list[dict[str, Any]] = field(default_factory=list)
    watchlist: list[dict[str, Any]] = field(default_factory=list)
    sector_weights: list[dict[str, Any]] = field(default_factory=list)
    realized_pnl: float = 0.0
    trades: list[dict[str, Any]] = field(default_factory=list)
    intraday_trades: list[dict[str, Any]] = field(default_factory=list)
    watchlist_changes: list[dict[str, Any]] = field(default_factory=list)
    watchlist_min_size: int = 5
    notes: list[str] = field(default_factory=list)
    reason_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "start_total": self.start_total,
            "end_total": self.end_total,
            "daily_pnl": self.daily_pnl,
            "daily_pnl_pct": self.daily_pnl_pct,
            "cash": self.cash,
            "cash_ratio": self.cash_ratio,
            "cash_delta": self.cash_delta,
            "stock_mv": self.stock_mv,
            "stock_ratio": self.stock_ratio,
            "holdings_count": self.holdings_count,
            "watchlist_count": self.watchlist_count,
            "max_weight_pct": self.max_weight_pct,
            "winners": self.winners,
            "losers": self.losers,
            "flat": self.flat,
            "day_mv_change": self.day_mv_change,
            "total_unrealized": self.total_unrealized,
            "position_change": self.position_change,
            "holdings": self.holdings,
            "watchlist": self.watchlist,
            "sector_weights": self.sector_weights,
            "realized_pnl": self.realized_pnl,
            "trades": self.trades,
            "intraday_trades": self.intraday_trades,
            "watchlist_changes": self.watchlist_changes,
            "watchlist_min_size": self.watchlist_min_size,
            "notes": self.notes,
            "reason_lines": self.reason_lines,
        }


def _recalc_portfolio_totals(portfolio: dict[str, Any], enriched: dict[str, dict[str, Any]]) -> None:
    from agent_reach.daily_run.portfolio_manager import _recalc_totals

    _recalc_totals(portfolio, enriched)


def _morning_portfolio(baseline: dict[str, Any]) -> dict[str, Any]:
    pf = dict(baseline.get("portfolio") or {})
    watchlist = baseline.get("watchlist") or pf.get("watchlist") or []
    if watchlist:
        pf["watchlist"] = [dict(w) for w in watchlist]
    return pf


def _holdings_map(portfolio: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for h in portfolio.get("holdings") or []:
        code = _normalize_code(str(h.get("code", "")))
        if code:
            out[code] = int(h.get("shares") or 0)
    return out


def _describe_position_change(morning_pf: dict[str, Any], close_pf: dict[str, Any]) -> str:
    morning = _holdings_map(morning_pf)
    close = _holdings_map(close_pf)
    if not morning:
        return "基线无持仓快照，跳过结构对比"
    added = sorted(set(close) - set(morning))
    removed = sorted(set(morning) - set(close))
    changed = sorted(
        code for code in set(morning) & set(close) if morning[code] != close[code]
    )
    parts: list[str] = []
    if added:
        parts.append(f"新增 {len(added)} 只")
    if removed:
        parts.append(f"卖出 {len(removed)} 只")
    if changed:
        parts.append(f"调仓 {len(changed)} 只")
    if not parts:
        return "持仓结构未变"
    return "，".join(parts)


def _watchlist_changes_from_adjust(watchlist_adjust: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    if not watchlist_adjust:
        return []
    return list(watchlist_adjust.get("changes") or [])


def _macro_avoid_watchlist_trim(wl_changes: list[dict[str, Any]]) -> bool:
    return any(
        c.get("action") == "remove" and "宏观回避" in str(c.get("reason") or "")
        for c in wl_changes
    )


def _watchlist_shortfall_line(
    watchlist_count: int,
    wl_min: int,
    wl_changes: list[dict[str, Any]],
) -> str:
    if watchlist_count >= wl_min:
        return ""
    if _macro_avoid_watchlist_trim(wl_changes):
        return (
            f"- ⚠️ 验证结论 **回避**，观察池收缩至 {watchlist_count} 只"
            f"（低于下限 {wl_min}；候选池仍有候补，宏观风控优先保留 Top {watchlist_count}）"
        )
    return f"- ⚠️ 观察池不足 {wl_min} 只（当前 {watchlist_count}），候选池已无可补标的"


def _format_ledger_trade_lines(trades: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for entry in trades:
        at = str(entry.get("at") or "")[:10]
        decision = entry.get("decision_action")
        for action in entry.get("actions") or []:
            side = "买入" if action.get("side") == "buy" else "卖出"
            name = action.get("name") or action.get("code") or "?"
            code = action.get("code") or "?"
            shares = action.get("shares")
            price = action.get("price")
            amount = action.get("amount")
            commission = float(action.get("commission") or 0)
            reason = str(action.get("reasoning") or "").strip()
            if shares and price:
                detail = f"{side} **{name}** ({code}) {shares}股 @ ¥{float(price):.2f}"
            else:
                detail = f"{side} **{name}** ({code})"
            if amount is not None:
                detail += f" · ¥{float(amount):,.0f}"
            if commission:
                detail += f"（费 ¥{commission:.2f}）"
            if at:
                detail = f"{at} {detail}"
            if decision and decision not in ("hold", "skip"):
                detail += f" · 信号 **{decision}**"
            if reason:
                detail += f" — {reason}"
            lines.append(f"- {detail}")
    return lines


def _format_intraday_trade_lines(trades: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for entry in trades:
        action = entry.get("action")
        if action in (None, "hold", "skip"):
            continue
        name = entry.get("name") or entry.get("code") or "?"
        code = entry.get("code") or "?"
        side = "买入" if action == "buy" else "卖出" if action == "sell" else str(action)
        reason = str(entry.get("reasoning") or entry.get("portfolio_message") or "").strip()
        shares = entry.get("shares")
        price = entry.get("price")
        line = f"- {side} **{name}** ({code})"
        if shares and price:
            line += f" {shares}股 @ ¥{float(price):.2f}"
        if reason:
            line += f" — {reason}"
        elif entry.get("lookback_mss") is not None:
            line += f" — Lookback MSS {entry.get('lookback_mss')}"
        if not entry.get("portfolio_applied", True):
            line += "（未落账）"
        lines.append(line)
        for act in entry.get("portfolio_actions") or []:
            sub = _format_ledger_trade_lines([{"at": entry.get("as_of"), "actions": [act]}])
            lines.extend(sub)
    return lines


def _holding_line(h: dict[str, Any]) -> str:
    name = h.get("name") or h.get("code")
    code = h.get("code")
    parts = [f"**{name}** ({code})"]
    if h.get("change_pct") is not None:
        parts.append(f"今日 {float(h['change_pct']):+.2f}%")
    if h.get("week_chg") is not None:
        parts.append(f"日内 {float(h['week_chg']):+,.0f}元")
    if h.get("unrealized_pnl") is not None:
        parts.append(f"浮盈 {float(h['unrealized_pnl']):+,.0f}元")
    if h.get("weight_pct") is not None:
        parts.append(f"权重 {float(h['weight_pct']):.1f}%")
    return "- " + " · ".join(parts)


def _attach_weights(holdings: list[dict[str, Any]], end_total: Optional[float]) -> list[dict[str, Any]]:
    denom = float(end_total) if end_total and end_total > 0 else sum(float(h.get("market_value") or 0) for h in holdings)
    out: list[dict[str, Any]] = []
    for h in holdings:
        row = dict(h)
        mv = float(row.get("market_value") or 0)
        row["weight_pct"] = round(mv / denom * 100, 1) if denom > 0 else None
        out.append(row)
    return out


def _build_reason_lines(data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    pnl = data.get("daily_pnl")
    pct = data.get("daily_pnl_pct")
    day_mv = data.get("day_mv_change")
    cash_delta = data.get("cash_delta")
    realized = float(data.get("realized_pnl") or 0)
    trades = data.get("trades") or []
    winners = int(data.get("winners") or 0)
    losers = int(data.get("losers") or 0)
    flat = int(data.get("flat") or 0)
    cash_ratio = data.get("cash_ratio")
    position_change = str(data.get("position_change") or "")
    notes = data.get("notes") or []

    if pnl is not None:
        pnl_f = float(pnl)
        pct_f = float(pct) if pct is not None else 0.0
        if pnl_f > 0 and pct_f >= 0.3:
            lines.append(f"组合盈利 **{pct_f:+.2f}%**（+¥{pnl_f:,.0f}），净值抬升。")
        elif pnl_f < 0 and pct_f <= -0.3:
            lines.append(f"组合回撤 **{pct_f:.2f}%**（¥{pnl_f:,.0f}），净值回落。")
        else:
            lines.append(f"组合净值基本持平（{pnl_f:+,.0f} 元，{pct_f:+.2f}%）。")
    elif notes:
        lines.append(notes[0] + "。")
    else:
        lines.append("缺少早盘净值基线，仅报告收盘持仓与现金。")

    if day_mv is not None and pnl is not None:
        gap = round(float(pnl) - float(day_mv), 2)
        if abs(gap) >= 50:
            lines.append(
                f"持股日内市值合计变动 **¥{float(day_mv):+,.0f}**，"
                f"与净值变动差额 **¥{gap:+,.0f}**（现金变动或成交口径所致）。"
            )
        elif winners or losers:
            lines.append(f"持股日内市值合计变动 **¥{float(day_mv):+,.0f}**。")

    perf_parts: list[str] = []
    if winners:
        perf_parts.append(f"{winners} 涨")
    if losers:
        perf_parts.append(f"{losers} 跌")
    if flat:
        perf_parts.append(f"{flat} 平")
    if perf_parts:
        lines.append("今日持仓表现：" + " / ".join(perf_parts) + "。")

    if cash_delta is not None and abs(float(cash_delta)) >= 1:
        sign = "增加" if float(cash_delta) > 0 else "减少"
        lines.append(f"现金较早盘{sign} **¥{abs(float(cash_delta)):,.0f}**。")

    if trades and abs(realized) > 0.01:
        sign = "+" if realized >= 0 else ""
        lines.append(f"今日成交 **{len(trades)}** 笔，ledger 净额 {sign}¥{realized:,.0f}。")
    elif position_change not in ("持仓结构未变", "基线无持仓快照，跳过结构对比"):
        lines.append(f"持仓变化：**{position_change}**。")
    else:
        lines.append("今日**无 ledger 成交**，以持仓波动为主。")

    wl_changes = data.get("watchlist_changes") or []
    wl_min = int(data.get("watchlist_min_size") or 5)
    watchlist_count = int(data.get("watchlist_count") or 0)
    if watchlist_count < wl_min and _macro_avoid_watchlist_trim(wl_changes):
        lines.append(
            f"验证结论 **回避**，观察池收缩至 {watchlist_count} 只（低于下限 {wl_min}）。"
        )

    if cash_ratio is not None:
        cr = float(cash_ratio)
        if cr >= 0.45:
            lines.append(f"现金占比 **{cr:.1%}**，仓位偏轻、偏防御。")
        elif cr <= 0.25:
            lines.append(f"现金占比 **{cr:.1%}**，仓位偏重。")

    total_unrealized = data.get("total_unrealized")
    if total_unrealized is not None and abs(float(total_unrealized)) >= 1000:
        lines.append(f"累计浮盈浮亏 **¥{float(total_unrealized):+,.0f}**（成本口径）。")

    return lines


def build_close_portfolio_summary(
    current: dict[str, Any],
    baseline: dict[str, Any],
    *,
    trades: Optional[list[dict[str, Any]]] = None,
    intraday_trades: Optional[list[dict[str, Any]]] = None,
    watchlist_adjust: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
    as_of: Optional[date] = None,
) -> ClosePortfolioSummary:
    """Build end-of-day portfolio summary from close snapshot vs morning baseline."""
    from agent_reach.daily_run.watchlist_manager import watchlist_min_size

    day = as_of or today_shanghai()
    wl_min = watchlist_min_size(settings or {})
    enriched = build_enriched_symbols(current)
    close_pf = portfolio_from_snapshot(current)
    morning_pf = _morning_portfolio(baseline)
    _recalc_portfolio_totals(close_pf, enriched)

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

    winners = losers = flat = 0
    day_mv_change = 0.0
    has_day_mv = False
    total_unrealized = 0.0
    max_weight: Optional[float] = None
    for h in holdings:
        chg = h.get("change_pct")
        if chg is not None:
            chg_f = float(chg)
            if chg_f > 0.05:
                winners += 1
            elif chg_f < -0.05:
                losers += 1
            else:
                flat += 1
        if h.get("week_chg") is not None:
            day_mv_change += float(h["week_chg"])
            has_day_mv = True
        if h.get("unrealized_pnl") is not None:
            total_unrealized += float(h["unrealized_pnl"])
        weight = h.get("weight_pct")
        if weight is not None:
            max_weight = max(max_weight or 0.0, float(weight))

    ledger_trades = _load_trade_ledger_range(day, day)
    realized = _compute_realized_pnl(ledger_trades)
    intraday_list = list(intraday_trades or [])
    wl_changes = _watchlist_changes_from_adjust(watchlist_adjust)

    cash = close_pf.get("cash")
    cash_ratio = close_pf.get("cash_ratio")
    morning_cash = morning_pf.get("cash")
    cash_delta: Optional[float] = None
    if cash is not None:
        cash = float(cash)
    if cash_ratio is not None:
        cash_ratio = float(cash_ratio)
    if cash is not None and morning_cash is not None:
        cash_delta = round(float(cash) - float(morning_cash), 2)

    stock_mv = round(float(end_total) - float(cash), 2) if end_total is not None and cash is not None else None
    stock_ratio = round(1 - float(cash_ratio), 4) if cash_ratio is not None else None

    summary = ClosePortfolioSummary(
        as_of=day.isoformat(),
        start_total=start_total,
        end_total=end_total,
        daily_pnl=daily_pnl,
        daily_pnl_pct=daily_pnl_pct,
        cash=cash,
        cash_ratio=cash_ratio,
        cash_delta=cash_delta,
        stock_mv=stock_mv,
        stock_ratio=stock_ratio,
        holdings_count=len(holdings),
        watchlist_count=len(watchlist),
        max_weight_pct=max_weight,
        winners=winners,
        losers=losers,
        flat=flat,
        day_mv_change=round(day_mv_change, 2) if has_day_mv else None,
        total_unrealized=round(total_unrealized, 2) if holdings else None,
        position_change=_describe_position_change(morning_pf, close_pf),
        holdings=holdings,
        watchlist=watchlist,
        sector_weights=[],
        realized_pnl=realized,
        trades=ledger_trades or list(trades or []),
        intraday_trades=intraday_list,
        watchlist_changes=wl_changes,
        watchlist_min_size=wl_min,
        notes=notes,
    )
    summary.reason_lines = _build_reason_lines(summary.to_dict())
    return summary


def render_close_portfolio_markdown(summary: ClosePortfolioSummary | dict[str, Any]) -> str:
    """Portfolio close summary: overview + per-stock P&L + trades + watchlist."""
    data = summary.to_dict() if isinstance(summary, ClosePortfolioSummary) else summary
    lines: list[str] = ["## 💰 组合盈亏"]

    if data.get("daily_pnl") is not None:
        pnl = float(data["daily_pnl"])
        sign = "+" if pnl >= 0 else ""
        pct_s = ""
        if data.get("daily_pnl_pct") is not None:
            pct = float(data["daily_pnl_pct"])
            pct_s = f"（{sign}{pct}%）"
        headline = f"**{sign}¥{pnl:,.0f}{pct_s}**"
        if data.get("start_total") is not None and data.get("end_total") is not None:
            lines.append(
                f"- {headline} · 早盘 ¥{float(data['start_total']):,.0f} → "
                f"收盘 ¥{float(data['end_total']):,.0f}"
            )
        else:
            lines.append(f"- {headline}")
    elif data.get("end_total") is not None:
        lines.append(f"- 收盘净值 **¥{float(data['end_total']):,.0f}**")
    else:
        lines.append("- 暂无完整净值数据")

    stock_ratio = data.get("stock_ratio")
    cash_ratio = data.get("cash_ratio")
    if stock_ratio is not None and cash_ratio is not None:
        lines.append(
            f"- 仓位：股票 **{float(stock_ratio):.1%}** / 现金 **{float(cash_ratio):.1%}**"
        )
    if data.get("realized_pnl") and abs(float(data["realized_pnl"])) > 0.01:
        realized = float(data["realized_pnl"])
        sign = "+" if realized >= 0 else ""
        lines.append(f"- 成交净额 {sign}¥{realized:,.0f}")

    lines.append("")
    lines.append("## 📈 个股盈亏")
    holdings = data.get("holdings") or []
    if holdings:
        for h in holdings:
            lines.append(_holding_line(h))
    else:
        lines.append("- 当前无持仓")

    lines.append("")
    lines.append("## 🔄 成交记录")
    trade_lines = _format_ledger_trade_lines(data.get("trades") or [])
    intraday_lines = _format_intraday_trade_lines(data.get("intraday_trades") or [])
    seen = set(trade_lines)
    merged_trades = trade_lines + [ln for ln in intraday_lines if ln not in seen]
    if merged_trades:
        lines.extend(merged_trades)
    else:
        lines.append("- 今日无成交")

    wl_min = int(data.get("watchlist_min_size") or 5)
    watchlist = data.get("watchlist") or []
    wl_changes = data.get("watchlist_changes") or []
    add_reasons = {
        _normalize_code(str(c.get("code", ""))): str(c.get("reason") or "")
        for c in wl_changes
        if c.get("action") == "add" and c.get("code")
    }
    fill_adds = [c for c in wl_changes if c.get("action") == "add"]

    lines.append("")
    lines.append(f"## 👀 观察池（{len(watchlist)} 只，下限 {wl_min}）")
    shortfall = _watchlist_shortfall_line(len(watchlist), wl_min, wl_changes)
    if shortfall:
        lines.append(shortfall)
    elif fill_adds:
        lines.append(f"- 本次补足 **{len(fill_adds)}** 只至下限 {wl_min}")

    if watchlist:
        for w in watchlist:
            code = _normalize_code(str(w.get("code", "")))
            name = w.get("name") or code
            chg_s = ""
            if w.get("change_pct") is not None:
                chg_s = f" · 今日 {float(w['change_pct']):+.2f}%"
            reason = add_reasons.get(code, "")
            if reason:
                lines.append(f"- **{name}** ({code}){chg_s} — {reason}")
            else:
                lines.append(f"- **{name}** ({code}){chg_s}")
    else:
        lines.append("- 观察池为空")

    lines.append("")
    lines.append("## 📝 原因摘要")
    for reason in data.get("reason_lines") or _build_reason_lines(data):
        lines.append(f"- {reason}")

    return "\n".join(lines).strip()

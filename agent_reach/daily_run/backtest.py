# -*- coding: utf-8
"""Minimal MSS threshold backtest for daily-run rule validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class BacktestMetrics:
    total_return: float
    benchmark_return: float
    excess_return: float
    max_drawdown: float
    trade_count: int
    win_rate: float
    days_in_market: int
    sharpe_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_return": round(self.total_return, 4),
            "benchmark_return": round(self.benchmark_return, 4),
            "excess_return": round(self.excess_return, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "trade_count": self.trade_count,
            "win_rate": round(self.win_rate, 4),
            "days_in_market": self.days_in_market,
            "sharpe_ratio": round(self.sharpe_ratio, 4),
        }


@dataclass
class BacktestResult:
    metrics: BacktestMetrics
    trades: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    def summary(self) -> str:
        m = self.metrics
        return (
            f"策略收益 {m.total_return:.2%} | 基准 {m.benchmark_return:.2%} | "
            f"超额 {m.excess_return:.2%} | 最大回撤 {m.max_drawdown:.2%} | "
            f"交易 {m.trade_count} 次 | 胜率 {m.win_rate:.1%}"
        )


def compute_sharpe_ratio(
    equity_curve: list[float],
    *,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
) -> float:
    """Annualized Sharpe from equity curve (StrategyOptimizer-style)."""
    if len(equity_curve) < 3:
        return 0.0
    daily_returns: list[float] = []
    for i in range(1, len(equity_curve)):
        prev = float(equity_curve[i - 1])
        if prev <= 0:
            continue
        daily_returns.append(float(equity_curve[i]) / prev - 1.0)
    if len(daily_returns) < 2:
        return 0.0
    rf_daily = risk_free_rate / periods_per_year
    excess = [r - rf_daily for r in daily_returns]
    mean = sum(excess) / len(excess)
    variance = sum((r - mean) ** 2 for r in excess) / len(excess)
    std = variance**0.5
    if std <= 0:
        return 0.0
    return (mean / std) * (periods_per_year**0.5)


def run_mss_backtest(
    history: list[dict[str, Any]],
    *,
    macro_veto: float = 40.0,
    aggressive_entry: float = 50.0,
    initial_capital: float = 100_000.0,
    commission_rate: float = 0.0015,
) -> BacktestResult:
    """
    Simple long-only MSS strategy on daily bars.

    Each history row expects:
      date, mss (or mss_final), return (daily stock/index return as decimal)
    Optional: benchmark_return
    """
    if len(history) < 2:
        raise ValueError("history 至少需要 2 个交易日")

    cash = initial_capital
    shares = 0.0
    entry_price = 0.0
    equity_curve: list[float] = [initial_capital]
    trades: list[dict[str, Any]] = []
    wins = 0
    trade_count = 0
    days_in_market = 0
    peak = initial_capital
    max_dd = 0.0
    bench_mult = 1.0

    sorted_rows = sorted(history, key=lambda r: str(r.get("date", "")))

    for row in sorted_rows:
        mss = float(row.get("mss_final", row.get("mss", 0)))
        daily_ret = float(row.get("return", 0))
        bench_ret = float(row.get("benchmark_return", daily_ret))
        price = float(row.get("price", 1.0))
        date = row.get("date", "")

        bench_mult *= 1 + bench_ret
        in_market = shares > 0

        # exit: macro veto while holding
        if in_market and mss < macro_veto:
            proceeds = shares * price * (1 - commission_rate)
            pnl = proceeds - (shares * entry_price)
            if pnl > 0:
                wins += 1
            trade_count += 1
            trades.append(
                {
                    "date": date,
                    "action": "sell",
                    "mss": mss,
                    "price": price,
                    "pnl": round(pnl, 2),
                    "reason": f"MSS {mss:.0f} < {macro_veto:.0f}",
                }
            )
            cash = proceeds
            shares = 0.0
            in_market = False

        # mark to market
        if in_market:
            equity = shares * price
            days_in_market += 1
        else:
            equity = cash

        # entry: aggressive threshold, flat
        if not in_market and mss >= aggressive_entry and cash > 0:
            shares = (cash * (1 - commission_rate)) / price
            entry_price = price
            cash = 0.0
            trades.append(
                {
                    "date": date,
                    "action": "buy",
                    "mss": mss,
                    "price": price,
                    "reason": f"MSS {mss:.0f} >= {aggressive_entry:.0f}",
                }
            )

        equity_curve.append(equity)
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)

    final_equity = equity_curve[-1]
    total_return = (final_equity / initial_capital) - 1
    benchmark_return = bench_mult - 1
    win_rate = wins / trade_count if trade_count else 0.0
    sharpe = compute_sharpe_ratio(equity_curve)

    metrics = BacktestMetrics(
        total_return=total_return,
        benchmark_return=benchmark_return,
        excess_return=total_return - benchmark_return,
        max_drawdown=max_dd,
        trade_count=trade_count,
        win_rate=win_rate,
        days_in_market=days_in_market,
        sharpe_ratio=sharpe,
    )
    return BacktestResult(metrics=metrics, trades=trades, equity_curve=equity_curve)


def render_backtest_markdown(result: BacktestResult) -> str:
    m = result.metrics
    lines = [
        f"**回测摘要：** {result.summary()}",
        "",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| 策略总收益 | {m.total_return:.2%} |",
        f"| 基准收益 | {m.benchmark_return:.2%} |",
        f"| 超额收益 | {m.excess_return:.2%} |",
        f"| 最大回撤 | {m.max_drawdown:.2%} |",
        f"| 交易次数 | {m.trade_count} |",
        f"| 胜率 | {m.win_rate:.1%} |",
        f"| 持仓天数 | {m.days_in_market} |",
        f"| Sharpe | {m.sharpe_ratio:.2f} |",
    ]
    if result.trades:
        lines.extend(["", "**最近交易：**"])
        for t in result.trades[-5:]:
            lines.append(
                f"- {t.get('date')} {t.get('action')} @ {t.get('price')} "
                f"(MSS {t.get('mss')}) — {t.get('reason')}"
            )
    return "\n".join(lines)

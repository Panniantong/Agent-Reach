# -*- coding: utf-8
"""Deterministic finance validators ported from dsh-finance (portfolio risk, reconcile, variance)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


def _finance_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("finance_close") or {})


def _round(value: float) -> float:
    return round(float(value), 2)


def _pct(value: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return round(float(value) / float(denominator) * 100, 2)


@dataclass
class PortfolioRiskSnapshot:
    net_liquidation: float
    cash: float
    cash_pct: float
    gross_exposure_pct: float
    largest_position: Optional[dict[str, Any]]
    largest_sector: Optional[dict[str, Any]]
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "net_liquidation": self.net_liquidation,
            "cash": self.cash,
            "cash_pct": self.cash_pct,
            "gross_exposure_pct": self.gross_exposure_pct,
            "largest_position": self.largest_position,
            "largest_sector": self.largest_sector,
            "flags": list(self.flags),
        }


@dataclass
class ReconciliationResult:
    reconciled: bool
    difference: float
    adjusted_book: float
    adjusted_source: float
    flags: list[str] = field(default_factory=list)
    sign_off_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "reconciled": self.reconciled,
            "difference": self.difference,
            "adjusted_book": self.adjusted_book,
            "adjusted_source": self.adjusted_source,
            "flags": list(self.flags),
            "sign_off_ready": self.sign_off_ready,
        }


@dataclass
class VarianceBridgeResult:
    base_value: float
    actual_value: float
    total_variance: float
    driver_total: float
    residual: float
    reconciled: bool
    material: bool
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_value": self.base_value,
            "actual_value": self.actual_value,
            "total_variance": self.total_variance,
            "driver_total": self.driver_total,
            "residual": self.residual,
            "reconciled": self.reconciled,
            "material": self.material,
            "flags": list(self.flags),
        }


def analyze_portfolio_risk(
    portfolio_summary: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> PortfolioRiskSnapshot:
    """Port of dsh-finance portfolio_risk_snapshot for A-share close portfolio."""
    cfg = _finance_cfg(settings)
    policy = {
        "max_position_pct": float(cfg.get("max_position_pct", 35)),
        "max_sector_pct": float(cfg.get("max_sector_pct", 50)),
        "max_gross_exposure_pct": float(cfg.get("max_gross_exposure_pct", 100)),
        "min_cash_pct": float(cfg.get("min_cash_pct", 5)),
    }

    end_total = portfolio_summary.get("end_total")
    cash = float(portfolio_summary.get("cash") or 0)
    if end_total is None or float(end_total) <= 0:
        return PortfolioRiskSnapshot(
            net_liquidation=0.0,
            cash=cash,
            cash_pct=0.0,
            gross_exposure_pct=0.0,
            largest_position=None,
            largest_sector=None,
            flags=["missing end_total"],
        )

    nav = float(end_total)
    positions: list[dict[str, Any]] = []
    sector_map: dict[str, float] = {}
    gross = 0.0

    for row in portfolio_summary.get("holdings") or []:
        shares = float(row.get("shares") or 0)
        price = row.get("week_end_price") or row.get("price")
        if shares <= 0 or price is None:
            continue
        mv = shares * float(price)
        gross += abs(mv)
        code = str(row.get("code") or "")
        name = str(row.get("name") or code)
        sector = str(row.get("sector") or row.get("industry") or "未分类")
        positions.append({"symbol": f"{name}({code})", "market_value": mv, "sector": sector})
        sector_map[sector] = sector_map.get(sector, 0.0) + abs(mv)

    positions.sort(key=lambda x: abs(float(x["market_value"])), reverse=True)
    sectors = sorted(
        [{"name": k, "market_value": v, "pct": _pct(v, nav)} for k, v in sector_map.items()],
        key=lambda x: x["pct"],
        reverse=True,
    )
    largest_position = None
    if positions:
        top = positions[0]
        largest_position = {
            "name": top["symbol"],
            "market_value": _round(top["market_value"]),
            "pct": _pct(abs(top["market_value"]), nav),
        }
    largest_sector = sectors[0] if sectors else None

    cash_pct = _pct(cash, nav)
    gross_pct = _pct(gross, nav)
    flags: list[str] = []
    if cash_pct < policy["min_cash_pct"]:
        flags.append(f"现金 {cash_pct}% 低于下限 {policy['min_cash_pct']}%")
    if gross_pct > policy["max_gross_exposure_pct"]:
        flags.append(f"总敞口 {gross_pct}% 超过上限 {policy['max_gross_exposure_pct']}%")
    if largest_position and largest_position["pct"] > policy["max_position_pct"]:
        flags.append(
            f"{largest_position['name']} 占比 {largest_position['pct']}% "
            f"超过上限 {policy['max_position_pct']}%"
        )
    if largest_sector and largest_sector["pct"] > policy["max_sector_pct"]:
        flags.append(
            f"{largest_sector['name']} 板块 {largest_sector['pct']}% "
            f"超过上限 {policy['max_sector_pct']}%"
        )

    return PortfolioRiskSnapshot(
        net_liquidation=_round(nav),
        cash=_round(cash),
        cash_pct=cash_pct,
        gross_exposure_pct=gross_pct,
        largest_position=largest_position,
        largest_sector=largest_sector,
        flags=flags,
    )


def reconcile_close_portfolio(
    portfolio_summary: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> ReconciliationResult:
    """Close NAV reconcile: start + daily_pnl + capital_flow ≈ end."""
    cfg = _finance_cfg(settings)
    tolerance = float(cfg.get("reconcile_tolerance_cny", 1.0))

    start = portfolio_summary.get("start_total")
    end = portfolio_summary.get("end_total")
    daily = float(portfolio_summary.get("daily_pnl") or 0)
    capital = float(portfolio_summary.get("capital_net_flow") or 0)
    flags: list[str] = []

    if start is None or end is None:
        return ReconciliationResult(
            reconciled=False,
            difference=0.0,
            adjusted_book=float(end or 0),
            adjusted_source=float(start or 0),
            flags=["缺少 start_total 或 end_total，无法对账"],
        )

    book = float(end)
    source = float(start) + daily + capital
    diff = _round(book - source)
    reconciled = abs(diff) <= tolerance
    if not reconciled:
        flags.append(f"收盘净值与期初+日盈亏+入出金差 {diff:+,.2f} 元")
    if capital and abs(capital) >= tolerance:
        flags.append(f"当日入出金 {capital:+,.0f} 元已纳入对账")

    return ReconciliationResult(
        reconciled=reconciled,
        difference=diff,
        adjusted_book=book,
        adjusted_source=_round(source),
        flags=flags,
        sign_off_ready=reconciled,
    )


def _variance_cfg(settings: Optional[dict[str, Any]], section: str) -> dict[str, float]:
    block = dict((settings or {}).get(section) or {})
    if section == "finance_close" and not block.get("variance_tolerance_cny"):
        block = {**_finance_cfg(settings), **block}
    return {
        "tolerance": float(block.get("variance_tolerance_cny", 1.0)),
        "materiality_cny": float(block.get("variance_materiality_cny", 500)),
        "materiality_pct": float(block.get("percent_materiality", 0.0)),
    }


def analyze_variance_bridge_values(
    base_value: Optional[float],
    actual_value: Optional[float],
    drivers: list[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
    section: str = "finance_close",
) -> VarianceBridgeResult:
    cfg = _variance_cfg(settings, section)
    if base_value is None or actual_value is None:
        return VarianceBridgeResult(
            base_value=0.0,
            actual_value=0.0,
            total_variance=0.0,
            driver_total=0.0,
            residual=0.0,
            reconciled=False,
            material=False,
            flags=["缺少 base/actual，无法构建 variance bridge"],
        )

    base = float(base_value)
    actual = float(actual_value)
    total = _round(actual - base)
    driver_total = _round(sum(float(d.get("amount") or 0) for d in drivers))
    residual = _round(total - driver_total)
    reconciled = abs(residual) <= cfg["tolerance"]
    flags: list[str] = []
    if not reconciled:
        flags.append(f"variance bridge 残差 {residual:+,.2f} 元")

    material = abs(total) >= cfg["materiality_cny"]
    if cfg["materiality_pct"] > 0 and base != 0:
        pct = abs(total / base * 100)
        material = material or pct >= cfg["materiality_pct"]
    if material:
        flags.append(f"变动 {total:+,.0f} 元达到 materiality 阈值")

    return VarianceBridgeResult(
        base_value=_round(base),
        actual_value=_round(actual),
        total_variance=total,
        driver_total=driver_total,
        residual=residual,
        reconciled=reconciled,
        material=material,
        flags=flags,
    )


def analyze_close_variance_bridge(
    portfolio_summary: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> VarianceBridgeResult:
    """Variance bridge for NAV change (dsh-finance finance_variance_bridge style)."""
    drivers = [
        {"name": "daily_pnl", "amount": float(portfolio_summary.get("daily_pnl") or 0)},
        {"name": "capital_net_flow", "amount": float(portfolio_summary.get("capital_net_flow") or 0)},
    ]
    return analyze_variance_bridge_values(
        portfolio_summary.get("start_total"),
        portfolio_summary.get("end_total"),
        drivers,
        settings=settings,
        section="finance_close",
    )


def _variance_cfg_section(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("finance_variance") or {})


def analyze_weekly_variance_bridge(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> VarianceBridgeResult:
    """Weekly PnL waterfall: stock vs cash drivers (dsh-finance variance-analysis)."""
    drivers: list[dict[str, Any]] = []
    if report.get("stock_pnl") is not None:
        drivers.append({"name": "stock_mv", "amount": float(report["stock_pnl"])})
    if report.get("cash_pnl") is not None:
        drivers.append({"name": "cash", "amount": float(report["cash_pnl"])})
    if not drivers and report.get("weekly_pnl") is not None:
        drivers.append({"name": "weekly_pnl", "amount": float(report["weekly_pnl"])})
    return analyze_variance_bridge_values(
        report.get("start_total"),
        report.get("end_total"),
        drivers,
        settings=settings,
        section="finance_variance",
    )


def _close_plan_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("finance_close_plan") or {})


def build_close_management_plan(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    skill_writeback: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """T+1..T+5 next-week close calendar (dsh-finance close-management style)."""
    cfg = _close_plan_cfg(settings)
    days = max(1, int(cfg.get("calendar_days", 5)))
    ws = str(report.get("week_start") or "")
    we = str(report.get("week_end") or "")

    blockers: list[str] = []
    tasks: list[dict[str, Any]] = []

    def _task(day: int, title: str, *, owner: str = "daily-run", dependency: str = "", blocker: bool = False) -> None:
        tasks.append(
            {
                "day": f"T+{day}",
                "title": title,
                "owner": owner,
                "dependency": dependency,
                "status": "blocked" if blocker else "pending",
            }
        )
        if blocker:
            blockers.append(title)

    variance = analyze_weekly_variance_bridge(report, settings=settings)
    if not variance.reconciled:
        blockers.append(f"weekly variance 残差 {variance.residual:+,.2f}")
        _task(1, "复核本周 stock/cash 盈亏分解与 ledger", blocker=True)
    elif variance.material:
        _task(1, "复盘 material 周盈亏驱动与持仓贡献")

    daily_totals = report.get("daily_totals") or []
    close_days = {str(r.get("date")) for r in daily_totals if r.get("job") == "close"}
    if len(close_days) < 3:
        _task(2, "补全缺失交易日 close manifest / 收盘复盘", blocker=True)
        blockers.append("close manifest 覆盖不足")
    else:
        _task(2, "核对 cron close 任务与 job_health 零失败")

    improvements = report.get("process_improvements") or []
    high = [i for i in improvements if str(i.get("priority") or "").lower() == "high"]
    for idx, item in enumerate(high[:2], start=1):
        title = str(item.get("title") or "流程改进")
        _task(min(2 + idx, days), f"执行改进：{title}")

    gates = ((skill_writeback or {}).get("skill_audit") or {}).get("gates") or {}
    if gates and gates.get("ok") is False and not gates.get("skipped"):
        _task(3, "修复周六 skill gates 后再推送 weekly", blocker=True, dependency="skill_gates")
        blockers.append("skill gates 未通过")

    for item in report.get("skill_gate_failures") or []:
        _task(3, f"skill_gate：{item}", blocker=True)

    _task(min(4, days), "盘中 scan 与 quote 覆盖率 spot-check", owner="intraday")
    _task(min(4, days), "finance_close 对账 + variance bridge 日检", dependency="close")

    audit_rows = 0
    try:
        from agent_reach.daily_run.harness_weekly_narrative import load_apply_audit_in_window

        audit_rows = len(load_apply_audit_in_window(week_start=ws, week_end=we))
    except Exception:
        audit_rows = 0
    if audit_rows:
        _task(min(5, days), f"审阅本周 {audit_rows} 条 harness apply_audit")

    _task(days, "周五收盘后 weekly 预检：PnL / skill / harness 卡")

    critical_path = [t["title"] for t in tasks if t.get("status") == "blocked"] or [
        t["title"] for t in tasks[:3]
    ]
    return {
        "week_start": ws,
        "week_end": we,
        "calendar_days": days,
        "tasks": tasks[: days + 2],
        "blockers": blockers,
        "critical_path": critical_path,
        "variance": variance.to_dict(),
    }


def run_finance_close_checks(
    portfolio_summary: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    risk = analyze_portfolio_risk(portfolio_summary, settings=settings)
    reconcile = reconcile_close_portfolio(portfolio_summary, settings=settings)
    variance = analyze_close_variance_bridge(portfolio_summary, settings=settings)
    blocking = [
        *([f"risk:{f}" for f in risk.flags]),
        *([f"reconcile:{f}" for f in reconcile.flags if not reconcile.reconciled]),
        *([f"variance:{f}" for f in variance.flags if not variance.reconciled]),
    ]
    return {
        "risk": risk.to_dict(),
        "reconcile": reconcile.to_dict(),
        "variance": variance.to_dict(),
        "passed": not blocking,
        "blocking_flags": blocking,
    }

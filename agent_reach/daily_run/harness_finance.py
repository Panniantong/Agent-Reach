# -*- coding: utf-8
"""Deterministic finance validators ported from dsh-finance (portfolio risk, reconcile, variance)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
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
class ReconciliationSnapshotResult:
    """dsh-finance finance_reconciliation_snapshot style open-item aging."""

    open_items: list[dict[str, Any]] = field(default_factory=list)
    category_totals: dict[str, float] = field(default_factory=dict)
    aging_buckets: dict[str, int] = field(default_factory=dict)
    stale_flags: list[str] = field(default_factory=list)
    sign_off_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "open_items": list(self.open_items),
            "category_totals": dict(self.category_totals),
            "aging_buckets": dict(self.aging_buckets),
            "stale_flags": list(self.stale_flags),
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


def _parse_day(value: Any) -> Optional[date]:
    text = str(value or "")[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _reconcile_snapshot_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    block = dict((settings or {}).get("finance_reconcile") or {})
    close = _finance_cfg(settings)
    return {
        "stale_days": int(block.get("stale_days") or close.get("reconcile_stale_days") or 3),
        "materiality_cny": float(block.get("materiality_cny") or close.get("reconcile_materiality_cny") or 500),
    }


def analyze_reconciliation_snapshot(
    portfolio_summary: dict[str, Any],
    reconcile: ReconciliationResult | dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> ReconciliationSnapshotResult:
    """Open-item aging / stale flags for close reconcile (finance_reconciliation_snapshot)."""
    cfg = _reconcile_snapshot_cfg(settings)
    as_of = _parse_day(portfolio_summary.get("as_of")) or date.today()
    rec = reconcile if isinstance(reconcile, ReconciliationResult) else ReconciliationResult(
        reconciled=bool(reconcile.get("reconciled")),
        difference=float(reconcile.get("difference") or 0),
        adjusted_book=float(reconcile.get("adjusted_book") or 0),
        adjusted_source=float(reconcile.get("adjusted_source") or 0),
        flags=list(reconcile.get("flags") or []),
        sign_off_ready=bool(reconcile.get("sign_off_ready")),
    )

    open_items: list[dict[str, Any]] = []
    category_totals: dict[str, float] = {}
    aging_buckets: dict[str, int] = {"0d": 0, "1-3d": 0, "4-7d": 0, "8d+": 0}
    stale_flags: list[str] = []

    def _add_item(
        category: str,
        label: str,
        *,
        amount: float = 0.0,
        item_date: Optional[date] = None,
        severity: str = "review",
    ) -> None:
        age_days = max(0, (as_of - item_date).days) if item_date else 0
        if age_days == 0:
            aging_buckets["0d"] += 1
        elif age_days <= 3:
            aging_buckets["1-3d"] += 1
        elif age_days <= 7:
            aging_buckets["4-7d"] += 1
        else:
            aging_buckets["8d+"] += 1
        category_totals[category] = category_totals.get(category, 0.0) + abs(amount)
        open_items.append(
            {
                "category": category,
                "label": label,
                "amount": _round(amount),
                "age_days": age_days,
                "severity": severity,
            }
        )
        if age_days >= cfg["stale_days"] and abs(amount) >= cfg["materiality_cny"]:
            stale_flags.append(f"stale {category}: {label} ({age_days}d)")

    if not rec.reconciled:
        _add_item(
            "nav_gap",
            f"NAV 对账差 {rec.difference:+,.2f} 元",
            amount=rec.difference,
            item_date=as_of,
            severity="blocking",
        )

    capital = float(portfolio_summary.get("capital_net_flow") or 0)
    if abs(capital) >= cfg["materiality_cny"]:
        _add_item(
            "capital_flow",
            f"当日入出金 {capital:+,.0f} 元待复核",
            amount=capital,
            item_date=as_of,
        )

    for entry in portfolio_summary.get("trades") or []:
        entry_day = _parse_day(entry.get("at"))
        for action in entry.get("actions") or []:
            side = str(action.get("side") or "").lower()
            code = str(action.get("code") or "")
            if side == "sell" and float(action.get("cost_basis") or 0) <= 0.01:
                _add_item(
                    "missing_cost_basis",
                    f"{code} 卖出缺 cost_basis",
                    amount=float(action.get("amount") or 0),
                    item_date=entry_day,
                )
            if side == "buy" and not str(action.get("reasoning") or "").strip():
                _add_item(
                    "missing_memo",
                    f"{code} 买入缺 reasoning",
                    amount=float(action.get("amount") or 0),
                    item_date=entry_day,
                )

    for row in portfolio_summary.get("holdings") or []:
        shares = float(row.get("shares") or 0)
        price = row.get("week_end_price") or row.get("price")
        if shares > 0 and (price is None or float(price) <= 0):
            code = str(row.get("code") or "")
            _add_item(
                "missing_price",
                f"{code} 持仓缺市价",
                amount=0.0,
                item_date=as_of,
            )

    sign_off_ready = rec.reconciled and not stale_flags and not any(
        i.get("severity") == "blocking" for i in open_items
    )
    return ReconciliationSnapshotResult(
        open_items=open_items,
        category_totals={k: _round(v) for k, v in category_totals.items()},
        aging_buckets=aging_buckets,
        stale_flags=stale_flags,
        sign_off_ready=sign_off_ready,
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
    snapshot = analyze_reconciliation_snapshot(portfolio_summary, reconcile, settings=settings)
    blocking = [
        *([f"risk:{f}" for f in risk.flags]),
        *([f"reconcile:{f}" for f in reconcile.flags if not reconcile.reconciled]),
        *([f"variance:{f}" for f in variance.flags if not variance.reconciled]),
        *([f"snapshot:{f}" for f in snapshot.stale_flags]),
    ]
    return {
        "risk": risk.to_dict(),
        "reconcile": reconcile.to_dict(),
        "reconcile_snapshot": snapshot.to_dict(),
        "variance": variance.to_dict(),
        "passed": not blocking,
        "blocking_flags": blocking,
    }


def _statements_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("finance_statements") or {})


def build_weekly_financial_statements(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Weekly income / balance / cash-flow skeleton (dsh-finance financial-statements)."""
    cfg = _statements_cfg(settings)
    materiality = float(cfg.get("materiality_cny") or 1000)

    end_total = report.get("end_total")
    start_total = report.get("start_total")
    cash = float(report.get("cash") or 0)
    weekly_pnl = float(report.get("weekly_pnl") or 0) if report.get("weekly_pnl") is not None else None
    stock_pnl = float(report.get("stock_pnl") or 0) if report.get("stock_pnl") is not None else None
    cash_pnl = float(report.get("cash_pnl") or 0) if report.get("cash_pnl") is not None else None

    holdings_mv = 0.0
    for row in report.get("holdings") or []:
        shares = float(row.get("shares") or 0)
        price = row.get("week_end_price") or row.get("price")
        if shares > 0 and price is not None:
            holdings_mv += shares * float(price)
    if end_total is not None and holdings_mv <= 0:
        holdings_mv = max(0.0, float(end_total) - cash)

    income_statement = {
        "period": f"{report.get('week_start')}~{report.get('week_end')}",
        "revenue": weekly_pnl,
        "stock_pnl": stock_pnl,
        "cash_pnl": cash_pnl,
        "net_income": weekly_pnl,
        "material": abs(weekly_pnl or 0) >= materiality if weekly_pnl is not None else False,
    }
    balance_sheet = {
        "as_of": report.get("week_end"),
        "assets_total": end_total,
        "cash": _round(cash),
        "investments": _round(holdings_mv),
        "equity": end_total,
        "start_equity": start_total,
    }
    cash_flow = {
        "operating": weekly_pnl,
        "investing": stock_pnl,
        "financing": report.get("capital_net_flow"),
        "net_change": weekly_pnl,
    }

    flags: list[str] = []
    if start_total is None or end_total is None:
        flags.append("缺少周初/周末净值")
    if weekly_pnl is not None and start_total and float(start_total) > 0:
        implied = float(end_total or 0) - float(start_total)
        if abs(implied - weekly_pnl) > float(cfg.get("tie_tolerance_cny") or 5.0):
            flags.append(f"损益与净值变动差 {abs(implied - weekly_pnl):,.2f} 元")

    return {
        "income_statement": income_statement,
        "balance_sheet": balance_sheet,
        "cash_flow": cash_flow,
        "material": bool(income_statement.get("material")),
        "flags": flags,
        "reconciled": not flags,
    }


def _ledger_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("finance_ledger") or {})


@dataclass
class JournalEntryCheckResult:
    period: Optional[str]
    entries_checked: int
    actions_checked: int
    total_debit: float
    total_credit: float
    difference: float
    balanced: bool
    ready_for_review: bool
    blocking_flags: list[str] = field(default_factory=list)
    review_flags: list[str] = field(default_factory=list)
    posting_authorized: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "entries_checked": self.entries_checked,
            "actions_checked": self.actions_checked,
            "total_debit": self.total_debit,
            "total_credit": self.total_credit,
            "difference": self.difference,
            "balanced": self.balanced,
            "ready_for_review": self.ready_for_review,
            "blocking_flags": list(self.blocking_flags),
            "review_flags": list(self.review_flags),
            "posting_authorized": self.posting_authorized,
        }


def check_trade_ledger_journal(
    trades: list[dict[str, Any]],
    *,
    portfolio_summary: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> JournalEntryCheckResult:
    """Port of dsh-finance finance_journal_entry_check for trade ledger lines."""
    cfg = _ledger_cfg(settings)
    tolerance = float(cfg.get("amount_tolerance_cny", 1.0))
    pct_tol = float(cfg.get("amount_tolerance_pct", 0.02))
    require_trade_id = bool(cfg.get("require_trade_id"))
    require_reasoning = bool(cfg.get("require_reasoning"))

    blocking: list[str] = []
    review: list[str] = []
    total_debit = 0.0
    total_credit = 0.0
    actions_checked = 0
    period = None
    if portfolio_summary:
        period = str(portfolio_summary.get("as_of") or "")[:10] or None

    for entry_idx, entry in enumerate(trades or []):
        entry_at = str(entry.get("at") or "")
        if not period and entry_at:
            period = entry_at[:10]
        trade_id = entry.get("trade_id")
        if require_trade_id and not str(trade_id or "").strip():
            review.append(f"entry {entry_idx + 1} missing trade_id")
        actions = entry.get("actions") or []
        if not actions:
            blocking.append(f"entry {entry_idx + 1} has no actions")
            continue
        for action_idx, action in enumerate(actions):
            actions_checked += 1
            line_no = f"entry {entry_idx + 1} action {action_idx + 1}"
            side = str(action.get("side") or "").lower()
            if side not in {"buy", "sell"}:
                blocking.append(f"{line_no} invalid side")
                continue
            code = str(action.get("code") or "").strip()
            if not code:
                blocking.append(f"{line_no} missing code")
            shares = int(action.get("shares") or 0)
            if shares <= 0:
                blocking.append(f"{line_no} shares must be positive")
                continue
            price = float(action.get("price") or 0)
            amount = float(action.get("amount") or 0)
            commission = float(action.get("commission") or 0)
            if price <= 0 and amount <= 0:
                blocking.append(f"{line_no} missing price/amount")
            implied = shares * price if price > 0 else amount
            if implied > 0 and amount > 0:
                diff = abs(amount - implied)
                limit = max(tolerance, implied * pct_tol)
                if diff > limit:
                    blocking.append(
                        f"{line_no} amount {amount:.2f} vs shares*price {implied:.2f} (Δ{diff:.2f})"
                    )
            if require_reasoning and not str(action.get("reasoning") or "").strip():
                review.append(f"{line_no} missing reasoning/memo")

            if side == "buy":
                debit = credit = amount + commission
            else:
                cost_basis = float(action.get("cost_basis") or 0)
                realized = action.get("realized_pnl")
                proceeds = amount - commission
                if cost_basis <= 0.01:
                    review.append(f"{line_no} sell missing cost_basis — run pnl backfill")
                    credit = proceeds
                    debit = proceeds
                else:
                    realized_f = float(realized if realized is not None else proceeds - cost_basis)
                    debit = proceeds
                    credit = cost_basis + realized_f
                    if abs(debit - credit) > tolerance:
                        blocking.append(
                            f"{line_no} sell journal out of balance by {abs(debit - credit):.2f}"
                        )
            total_debit += debit
            total_credit += credit

    pf = portfolio_summary or {}
    pf_trades = pf.get("trades") or []
    if pf_trades and not trades:
        blocking.append("portfolio has trades but empty ledger input")
    if trades and pf.get("trade_cash_flow") is not None:
        from agent_reach.daily_run.realized_pnl import compute_trade_cash_flow

        ledger_flow = compute_trade_cash_flow(trades)
        pf_flow = float(pf["trade_cash_flow"])
        if abs(ledger_flow - pf_flow) > tolerance:
            review.append(
                f"trade_cash_flow ledger {ledger_flow:+,.2f} vs portfolio {pf_flow:+,.2f}"
            )

    difference = _round(total_debit - total_credit)
    balanced = abs(difference) <= tolerance and not blocking
    ready = balanced and not review
    return JournalEntryCheckResult(
        period=period,
        entries_checked=len(trades or []),
        actions_checked=actions_checked,
        total_debit=_round(total_debit),
        total_credit=_round(total_credit),
        difference=difference,
        balanced=balanced,
        ready_for_review=ready,
        blocking_flags=blocking,
        review_flags=review,
    )


def run_finance_ledger_checks(
    portfolio_summary: dict[str, Any],
    *,
    trades: Optional[list[dict[str, Any]]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    day_trades = trades if trades is not None else list(portfolio_summary.get("trades") or [])
    journal = check_trade_ledger_journal(
        day_trades,
        portfolio_summary=portfolio_summary,
        settings=settings,
    )
    blocking = list(journal.blocking_flags)
    if not day_trades and (portfolio_summary.get("intraday_trades") or portfolio_summary.get("realized_sells")):
        review_note = "有成交摘要但 ledger 为空"
        journal.review_flags.append(review_note)
    return {
        "journal": journal.to_dict(),
        "passed": journal.balanced and not blocking,
        "blocking_flags": blocking,
    }

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


def analyze_close_variance_bridge(
    portfolio_summary: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> VarianceBridgeResult:
    """Variance bridge for NAV change (dsh-finance finance_variance_bridge style)."""
    cfg = _finance_cfg(settings)
    tolerance = float(cfg.get("variance_tolerance_cny", 1.0))
    materiality = float(cfg.get("variance_materiality_cny", 500))

    start = portfolio_summary.get("start_total")
    end = portfolio_summary.get("end_total")
    if start is None or end is None:
        return VarianceBridgeResult(
            base_value=0.0,
            actual_value=0.0,
            total_variance=0.0,
            driver_total=0.0,
            residual=0.0,
            reconciled=False,
            material=False,
            flags=["缺少 start/end，无法构建 variance bridge"],
        )

    base = float(start)
    actual = float(end)
    total = _round(actual - base)
    drivers = [
        {"name": "daily_pnl", "amount": float(portfolio_summary.get("daily_pnl") or 0)},
        {"name": "capital_net_flow", "amount": float(portfolio_summary.get("capital_net_flow") or 0)},
    ]
    driver_total = _round(sum(d["amount"] for d in drivers))
    residual = _round(total - driver_total)
    reconciled = abs(residual) <= tolerance
    flags: list[str] = []
    if not reconciled:
        flags.append(f"variance bridge 残差 {residual:+,.2f} 元")
    material = abs(total) >= materiality
    if material:
        flags.append(f"日净值变动 {total:+,.0f} 元达到 materiality 阈值 {materiality:,.0f}")

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

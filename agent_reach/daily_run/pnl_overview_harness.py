# -*- coding: utf-8
"""PnL overview (realized + unrealized) → harness self-evolution."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement
from agent_reach.daily_run.realized_pnl import PnlOverview, build_pnl_overview


def _pnl_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("pnl_overview") or {})


def pnl_overview_to_harness_evidence(
    overview: PnlOverview | dict[str, Any],
    *,
    portfolio_summary: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    data = overview.to_dict() if isinstance(overview, PnlOverview) else overview
    pf = portfolio_summary or {}
    cfg = _pnl_cfg(settings)

    large_unreal_cny = float(cfg.get("large_unrealized_loss_cny", 5000))
    large_real_cny = float(cfg.get("large_realized_loss_cny", 500))
    large_unreal_pct = float(cfg.get("large_unrealized_loss_pct", 10))

    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    realized = float(data.get("realized_pnl") or 0)
    unrealized = float(data.get("unrealized_pnl") or 0)
    total = float(data.get("total_pnl") or 0)
    wins = int(data.get("win_count") or 0)
    losses = int(data.get("loss_count") or 0)

    daily_pnl = pf.get("daily_pnl")
    daily_pct = pf.get("daily_pnl_pct")
    if daily_pnl is not None:
        sign = "+" if float(daily_pnl) >= 0 else ""
        pct_s = f"（{float(daily_pct):+.2f}%）" if daily_pct is not None else ""
        memory.append(f"盈亏总览：当日组合 {sign}¥{float(daily_pnl):,.0f}{pct_s}")

    memory.append(
        f"累计已实现 {realized:+,.0f} · 浮动 {unrealized:+,.0f} · 合计 {total:+,.0f}"
    )
    if wins or losses:
        memory.append(f"卖出胜率：{wins} 盈 / {losses} 亏")

    capital_flow = pf.get("capital_net_flow")
    if capital_flow is not None and abs(float(capital_flow)) >= 1:
        memory.append(f"当日入出金已剔除：{float(capital_flow):+,.0f} 元（PnL 口径）")
        playbook.append("有外部入金/出金时用 daily-run capital 记录，避免日PnL失真")

    for row in data.get("realized_sells") or []:
        name = row.get("name") or row.get("code") or "?"
        code = row.get("code") or "?"
        pnl = float(row.get("realized_pnl") or 0)
        pct = row.get("realized_pnl_pct")
        cost_basis = float(row.get("cost_basis") or 0)
        pct_s = f"（{float(pct):+.2f}%）" if pct is not None else ""
        line = f"卖出 {name}({code}) 已实现 {pnl:+,.0f}{pct_s}"
        memory.append(line)

        if cost_basis <= 0.01 and int(row.get("shares") or 0) > 0:
            playbook.append(
                f"{name}({code}) ledger 缺买入成本，运行 daily-run pnl backfill 或补录历史买入"
            )
            plan.append(f"pnl：补全 {code} 成本基准后再评估卖出策略")

        if pnl <= -large_real_cny:
            policy.append(f"已实现亏损较大：{name} 卖出后复盘入场/止损纪律")
            plan.append(f"pnl：{name} 亏损 {pnl:,.0f}，下日 verify 偏防御")
        elif pnl >= large_real_cny:
            playbook.append(f"止盈参考：{name} 已实现 +{pnl:,.0f}，同类标的可分批兑现")

    for h in data.get("holdings") or []:
        up = float(h.get("unrealized_pnl") or 0)
        pct = h.get("unrealized_pnl_pct")
        name = h.get("name") or h.get("code") or "?"
        code = h.get("code") or "?"
        if up <= -large_unreal_cny or (
            pct is not None and float(pct) <= -large_unreal_pct
        ):
            memory.append(f"浮亏警示 {name}({code}) {up:+,.0f}" + (f"（{float(pct):+.1f}%）" if pct is not None else ""))
            if up <= -large_unreal_cny * 2:
                policy.append(f"深浮亏 {name}：禁止接飞刀加仓，优先 verify 回避/减仓")
                plan.append(f"pnl：审视 {code} 止损/减仓阈值")
            else:
                plan.append(f"pnl：跟踪 {code} 浮亏收敛或触发 defensive_trim")

    if total < -large_unreal_cny and unrealized < realized:
        policy.append("浮动亏损主导净值：维持高现金，减少新开仓")
    if realized > 0 and unrealized < 0 and abs(unrealized) > abs(realized):
        playbook.append("已实现盈利但浮亏拖累：优先处理浮亏最大持仓")

    trade_cash = float(data.get("trade_cash_flow") or 0)
    if trade_cash and abs(trade_cash - realized) > large_real_cny:
        playbook.append("成交净额与已实现盈亏口径不同：报告以 FIFO realized 为准")

    summary = (
        f"pnl_overview realized={realized:+.0f} unrealized={unrealized:+.0f} "
        f"sells={len(data.get('realized_sells') or [])}"
    )
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def build_close_pnl_overview(
    portfolio_summary: Optional[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> PnlOverview:
    pf: dict[str, Any] = {"holdings": []}
    if portfolio_summary:
        pf["holdings"] = [
            {
                "code": h.get("code"),
                "name": h.get("name"),
                "shares": h.get("shares"),
                "cost": h.get("cost"),
                "price": h.get("week_end_price") or h.get("price"),
            }
            for h in portfolio_summary.get("holdings") or []
        ]
    as_of = str((portfolio_summary or {}).get("as_of") or "")[:10]
    end = date.fromisoformat(as_of) if as_of else None
    return build_pnl_overview(pf, start=date(1970, 1, 1), end=end)


def apply_pnl_overview_harness_refinement(
    portfolio_summary: Optional[dict[str, Any]],
    *,
    overview: Optional[PnlOverview | dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not portfolio_summary:
        return {"skipped": True, "reason": "no portfolio_summary", "job": "pnl_overview"}
    ov = overview or build_close_pnl_overview(portfolio_summary, settings=settings)
    evidence = pnl_overview_to_harness_evidence(
        ov,
        portfolio_summary=portfolio_summary,
        settings=settings,
    )
    return apply_skill_refinement(
        "pnl_overview",
        evidence,
        settings=settings,
        enabled_flag="pnl_overview",
    )

# -*- coding: utf-8
"""PnL overview (realized + unrealized) → harness self-evolution."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement
from agent_reach.daily_run.pnl_execution_guard import ledger_cost_missing, sell_loss_streak
from agent_reach.daily_run.realized_pnl import (
    PnlOverview,
    build_pnl_overview,
    format_buy_trade_line,
    format_holding_trade_line,
    format_sell_trade_line,
)


def _pnl_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("pnl_overview") or {})


def _pnl_thresholds(settings: Optional[dict[str, Any]]) -> dict[str, float]:
    """Harness-evolved PnL thresholds (fallback to pnl_overview static config)."""
    from agent_reach.daily_run.harness_policy import (
        deep_loss_policy_default,
        deep_loss_tier_cny_threshold,
    )

    cfg = settings or {}
    return {
        "loss_cny": deep_loss_policy_default(cfg, "loss_cny_threshold"),
        "loss_pct": deep_loss_policy_default(cfg, "loss_pct_threshold"),
        "realized_loss": deep_loss_policy_default(cfg, "realized_loss_threshold"),
        "realized_gain": deep_loss_policy_default(cfg, "realized_gain_threshold"),
        "deep_loss_tier_cny": deep_loss_tier_cny_threshold(cfg),
        "portfolio_loss": deep_loss_policy_default(cfg, "portfolio_loss_cny_threshold"),
        "tier_multiplier": deep_loss_policy_default(cfg, "deep_loss_tier_multiplier"),
        "cover_ratio": deep_loss_policy_default(cfg, "cover_ratio"),
        "sell_ratio": deep_loss_policy_default(cfg, "sell_ratio"),
        "coverable_realized_weight": deep_loss_policy_default(cfg, "coverable_realized_weight"),
        "win_rate_min": deep_loss_policy_default(cfg, "win_rate_min"),
        "loss_streak_max": deep_loss_policy_default(cfg, "loss_streak_max"),
        "ledger_cost_tolerance": deep_loss_policy_default(cfg, "ledger_cost_tolerance_cny"),
    }


def pnl_overview_to_harness_evidence(
    overview: PnlOverview | dict[str, Any],
    *,
    portfolio_summary: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    data = overview.to_dict() if isinstance(overview, PnlOverview) else overview
    pf = portfolio_summary or {}
    thr = _pnl_thresholds(settings)

    large_unreal_cny = thr["loss_cny"]
    large_real_cny = thr["realized_loss"]
    large_gain_cny = thr["realized_gain"]
    large_unreal_pct = thr["loss_pct"]
    deep_loss_tier_cny = thr["deep_loss_tier_cny"]
    portfolio_loss_cny = thr["portfolio_loss"]

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
        total_sells = wins + losses
        win_rate_min = thr["win_rate_min"]
        if win_rate_min > 0 and total_sells >= 3:
            win_rate = wins / total_sells
            if win_rate < win_rate_min:
                policy.append(
                    f"卖出胜率偏低：{wins}盈/{losses}亏（<{win_rate_min:.0%}）"
                )
                plan.append("pnl：下日提高入场门槛，减少新开仓")
        loss_streak_max = int(thr["loss_streak_max"])
        streak = sell_loss_streak(data.get("realized_sells") or [])
        if loss_streak_max > 0 and streak >= loss_streak_max:
            policy.append(f"连亏警戒：连续{streak}笔卖出亏损")
            plan.append("pnl：连亏后优先 verify 回避，暂缓加仓")

    capital_flow = pf.get("capital_net_flow")
    if capital_flow is not None and abs(float(capital_flow)) >= 1:
        memory.append(f"当日入出金已剔除：{float(capital_flow):+,.0f} 元（PnL 口径）")
        playbook.append("有外部入金/出金时用 daily-run capital 记录，避免日PnL失真")

    for row in data.get("buys") or []:
        memory.append(format_buy_trade_line(row))

    for row in data.get("realized_sells") or []:
        name = row.get("name") or row.get("code") or "?"
        code = row.get("code") or "?"
        pnl = float(row.get("realized_pnl") or 0)
        cost_basis = float(row.get("cost_basis") or 0)
        memory.append(format_sell_trade_line(row))

        if ledger_cost_missing(row, thr["ledger_cost_tolerance"]):
            playbook.append(
                f"{name}({code}) ledger 缺买入成本，运行 daily-run pnl backfill 或补录历史买入"
            )
            plan.append(f"pnl：补全 {code} 成本基准后再评估卖出策略")
            policy.append(f"ledger 缺买入成本：{name}({code}) 成本基准不可靠")

        if pnl <= -large_real_cny:
            policy.append(f"已实现亏损较大：{name} 卖出后复盘入场/止损纪律")
            plan.append(f"pnl：{name} 亏损 {pnl:,.0f}，下日 verify 偏防御")
        elif pnl >= large_gain_cny:
            playbook.append(f"止盈参考：{name} 已实现 +{pnl:,.0f}，同类标的可分批兑现")

    for h in data.get("holdings") or []:
        memory.append(format_holding_trade_line(h))
        up = float(h.get("unrealized_pnl") or 0)
        pct = h.get("unrealized_pnl_pct")
        name = h.get("name") or h.get("code") or "?"
        code = h.get("code") or "?"
        if up <= -large_unreal_cny or (
            pct is not None and float(pct) <= -large_unreal_pct
        ):
            if up <= -deep_loss_tier_cny:
                policy.append(
                    f"深度套牢 {name}({code})：cover_ratio≥{thr['cover_ratio']:.0%}，"
                    f"sell_ratio≤{min(thr['sell_ratio'], 0.5):.0%}，"
                    f"卖出前需组合盈利覆盖浮亏"
                )
                plan.append(f"pnl：审视 {code} 止损/减仓阈值")
            else:
                plan.append(f"pnl：跟踪 {code} 浮亏收敛或触发 defensive_trim")

    if total < -portfolio_loss_cny and unrealized < realized:
        policy.append("浮动亏损主导净值：维持高现金，减少新开仓")
    if realized > 0 and unrealized < 0 and abs(unrealized) > abs(realized):
        playbook.append("已实现盈利但浮亏拖累：优先处理浮亏最大持仓")

    trade_cash = float(data.get("trade_cash_flow") or 0)
    if trade_cash and abs(trade_cash - realized) > large_real_cny:
        playbook.append("成交净额与已实现盈亏口径不同：报告以 FIFO realized 为准")

    summary = (
        f"pnl_overview realized={realized:+.0f} unrealized={unrealized:+.0f} "
        f"sells={len(data.get('realized_sells') or [])} "
        f"tier={deep_loss_tier_cny:.0f}"
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
                "acquired_date": h.get("acquired_date"),
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

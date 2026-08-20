# -*- coding: utf-8
"""Compare actual intraday sells vs current harness sell-ratio rules (close what-if)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from agent_reach.daily_run.portfolio_manager import deep_loss_policy, deep_loss_sell_analysis
from agent_reach.daily_run.snapshot_builder import _normalize_code
from agent_reach.daily_run.symbols import build_enriched_symbols


@dataclass
class SellRulesWhatIfResult:
    as_of: str
    policy_note: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    actual_realized_pnl: float = 0.0
    hypothetical_realized_pnl: float = 0.0
    realized_pnl_delta: float = 0.0
    skipped: bool = False
    skip_reason: str = ""
    scope: str = "daily"
    period_label: str = ""
    trading_days: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "policy_note": self.policy_note,
            "rows": self.rows,
            "actual_realized_pnl": self.actual_realized_pnl,
            "hypothetical_realized_pnl": self.hypothetical_realized_pnl,
            "realized_pnl_delta": self.realized_pnl_delta,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "scope": self.scope,
            "period_label": self.period_label,
            "trading_days": self.trading_days,
        }


@dataclass
class BuyRulesWhatIfResult:
    as_of: str
    policy_note: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    actual_buy_notional: float = 0.0
    hypothetical_buy_notional: float = 0.0
    buy_notional_delta: float = 0.0
    skipped: bool = False
    skip_reason: str = ""
    scope: str = "daily"
    period_label: str = ""
    trading_days: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "policy_note": self.policy_note,
            "rows": self.rows,
            "actual_buy_notional": self.actual_buy_notional,
            "hypothetical_buy_notional": self.hypothetical_buy_notional,
            "buy_notional_delta": self.buy_notional_delta,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "scope": self.scope,
            "period_label": self.period_label,
            "trading_days": self.trading_days,
        }


def _morning_portfolio(baseline: dict[str, Any]) -> dict[str, Any]:
    pf = dict(baseline.get("portfolio") or {})
    watchlist = baseline.get("watchlist") or pf.get("watchlist") or []
    if watchlist:
        pf["watchlist"] = [dict(w) for w in watchlist]
    return pf


def _aggregate_actual_sells(summary: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for entry in summary.get("trades") or []:
        for action in entry.get("actions") or []:
            if action.get("side") != "sell":
                continue
            code = _normalize_code(str(action.get("code", "")))
            if not code:
                continue
            out[code] = out.get(code, 0) + int(action.get("shares") or 0)
    return out


def _aggregate_actual_buys(summary: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for entry in summary.get("trades") or []:
        for action in entry.get("actions") or []:
            if action.get("side") != "buy":
                continue
            code = _normalize_code(str(action.get("code", "")))
            if not code:
                continue
            out[code] = out.get(code, 0) + int(action.get("shares") or 0)
    return out


def _buy_price_by_code(
    rows: list[dict[str, Any]],
    enriched: dict[str, dict[str, Any]],
) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in rows:
        code = str(row.get("code") or "")
        price = row.get("price")
        if price is not None and float(price) > 0:
            out[code] = float(price)
    for code, row in enriched.items():
        price = row.get("price")
        if price is not None and float(price) > 0:
            out.setdefault(code, float(price))
    return out


def _estimate_buy_notional(
    rows: list[dict[str, Any]],
    *,
    shares_key: str,
    prices: dict[str, float],
) -> float:
    total = 0.0
    for row in rows:
        code = str(row.get("code") or "")
        shares = int(row.get(shares_key) or 0)
        price = float(row.get("price") or prices.get(code) or 0)
        if shares > 0 and price > 0:
            total += shares * price
    return round(total, 2)


def _buy_policy_note(settings: dict[str, Any]) -> str:
    from agent_reach.daily_run.harness_policy import (
        _position_policy,
        aggressive_entry_default,
        macro_veto_default,
    )
    from agent_reach.daily_run.intraday_policy import effective_aggressive_entry

    policy = _position_policy(settings)
    deploy_ratio = float(policy.get("deploy_ratio", 1.0))
    max_pct = float(policy.get("max_position_pct", 35.0))
    macro_veto = macro_veto_default(settings)
    aggressive = effective_aggressive_entry(
        settings,
        "",
        aggressive_entry_default(settings),
        macro_veto=macro_veto,
    )
    return (
        f"deploy_ratio **{deploy_ratio:.0%}** · "
        f"max_position_pct **{max_pct:.0f}%** · "
        f"aggressive_entry **{aggressive:.0f}**"
    )


def _replay_evolved_buy_decision(
    entry: dict[str, Any],
    snapshot: dict[str, Any],
    settings: dict[str, Any],
) -> tuple[str, str]:
    """Replay intraday buy/sell decision under current evolved rules."""
    from agent_reach.daily_run.intraday import _decide_trade
    from agent_reach.daily_run.verdict import VerdictResult

    lookback_mss = float(entry.get("lookback_mss") or 0)
    trend = str(entry.get("trend") or "flat")
    mss_final = float(entry.get("mss_final") or lookback_mss)
    reasoning = str(entry.get("reasoning") or "")
    verdict_label = str(entry.get("verdict") or "观察")
    tag_blocked = "标签" in reasoning and "阻断买入" in reasoning

    verdict = VerdictResult(
        verdict=verdict_label,
        confidence="",
        mss_final=mss_final,
        entry_price=None,
        stop_loss_price=None,
        invalidation="",
        reasoning=reasoning,
        blocked=tag_blocked,
    )
    report = {
        "code": entry.get("code"),
        "name": entry.get("name"),
        "verdict": verdict_label,
        "mss_final": mss_final,
        "blocked": tag_blocked,
        "reasoning": reasoning,
    }
    snap = dict(snapshot)
    snap["code"] = entry.get("code")
    snap["name"] = entry.get("name")

    decision = _decide_trade(
        lookback_mss=lookback_mss,
        trend=trend,
        verdict=verdict,
        report=report,
        snapshot=snap,
        settings=settings,
        trade_index=1,
        expected_return_pct=entry.get("expected_return_pct"),
    )
    if decision.action == "buy" and not decision.blocked and not decision.friction_blocked:
        return "buy", ""
    if decision.action == "buy" and decision.friction_blocked:
        return "hold", "摩擦成本阻断"
    return str(decision.action or "hold"), str(decision.reasoning or "")


def _advance_pf_with_actions(
    pf: dict[str, Any],
    actions: list[dict[str, Any]],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
) -> dict[str, Any]:
    from agent_reach.daily_run.portfolio_manager import (
        _add_bought_shares,
        _recalc_totals,
        copy_portfolio,
        friction_commission_rate_default,
    )

    pf = copy_portfolio(pf)
    commission_rate = friction_commission_rate_default(settings)
    holdings = list(pf.get("holdings") or [])
    for action in actions or []:
        side = action.get("side")
        code = _normalize_code(str(action.get("code", "")))
        shares = int(action.get("shares") or 0)
        price = float(action.get("price") or enriched.get(code, {}).get("price") or 0)
        if shares <= 0 or price <= 0 or not code:
            continue
        if side == "buy":
            gross = shares * price
            commission = round(gross * commission_rate, 2)
            pf["cash"] = round(float(pf.get("cash") or 0) - gross - commission, 2)
            _add_bought_shares(
                holdings,
                code=code,
                name=str(action.get("name", code)),
                shares=shares,
                price=price,
            )
        elif side == "sell":
            gross = shares * price
            commission = round(gross * commission_rate, 2)
            pf["cash"] = round(float(pf.get("cash") or 0) + gross - commission, 2)
            updated: list[dict[str, Any]] = []
            for h in holdings:
                if _normalize_code(str(h.get("code", ""))) != code:
                    updated.append(h)
                    continue
                remain = int(h.get("shares") or 0) - shares
                if remain > 0:
                    row = dict(h)
                    row["shares"] = remain
                    updated.append(row)
            holdings = updated
    pf["holdings"] = holdings
    _recalc_totals(pf, enriched)
    return pf


def _merge_weekly_buy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("code") or "")
        if not code:
            continue
        if code not in merged:
            merged[code] = {
                **row,
                "block_reasons": [row["block_reason"]] if row.get("block_reason") else [],
            }
            continue
        target = merged[code]
        target["actual_bought"] = int(target.get("actual_bought") or 0) + int(row.get("actual_bought") or 0)
        target["hypothetical_bought"] = int(target.get("hypothetical_bought") or 0) + int(
            row.get("hypothetical_bought") or 0
        )
        target["share_delta"] = int(target["hypothetical_bought"]) - int(target["actual_bought"])
        if row.get("block_reason"):
            target.setdefault("block_reasons", []).append(row["block_reason"])
    out: list[dict[str, Any]] = []
    for row in merged.values():
        reasons = [str(r) for r in row.pop("block_reasons", []) if r]
        if reasons:
            row["block_reason"] = reasons[0] if len(reasons) == 1 else "；".join(dict.fromkeys(reasons))
        out.append(row)
    out.sort(key=lambda r: (-int(r.get("actual_bought") or 0), str(r.get("code") or "")))
    return out


def _day_has_buy(trades: list[dict[str, Any]]) -> bool:
    for entry in trades:
        for action in entry.get("actions") or []:
            if action.get("side") == "buy":
                return True
    return False


def _intraday_buy_actions(entry: dict[str, Any]) -> list[dict[str, Any]]:
    actions = [
        dict(a)
        for a in (entry.get("portfolio_actions") or [])
        if a.get("side") == "buy"
    ]
    if actions:
        return actions
    if entry.get("action") == "buy" and entry.get("shares") and entry.get("price"):
        return [
            {
                "side": "buy",
                "code": entry.get("code"),
                "name": entry.get("name"),
                "shares": entry.get("shares"),
                "price": entry.get("price"),
            }
        ]
    return []


def build_buy_rules_whatif(
    *,
    summary: dict[str, Any],
    baseline: dict[str, Any],
    current: dict[str, Any],
    intraday_trades: Optional[list[dict[str, Any]]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> BuyRulesWhatIfResult:
    """Replay intraday buy signals vs ledger buys under current harness buy rules."""
    from agent_reach.daily_run.portfolio_manager import simulate_buy_analysis
    from agent_reach.daily_run.settings import load_settings

    as_of = str(summary.get("as_of") or "")
    morning_pf = _morning_portfolio(baseline)
    cfg = settings or load_settings()
    enriched = build_enriched_symbols(current, cfg)
    actual_buys = _aggregate_actual_buys(summary)
    intraday_list = list(intraday_trades if intraday_trades is not None else summary.get("intraday_trades") or [])

    if not actual_buys and not any(
        str(e.get("action") or "") == "buy" or _intraday_buy_actions(e) for e in intraday_list
    ):
        return BuyRulesWhatIfResult(
            as_of=as_of,
            policy_note=_buy_policy_note(cfg),
            skipped=True,
            skip_reason="今日无买入相关成交或信号，跳过基准值 vs 自进化规则对比",
        )

    pf = dict(morning_pf)
    pf.setdefault("watchlist", list(morning_pf.get("watchlist") or baseline.get("watchlist") or []))
    row_accum: dict[str, dict[str, Any]] = {}

    for entry in intraday_list:
        code = _normalize_code(str(entry.get("code") or ""))
        if not code:
            continue
        snap = dict(current)
        snap["portfolio"] = pf
        snap["code"] = code
        snap["name"] = entry.get("name") or code

        actual_actions = _intraday_buy_actions(entry)
        actual_shares = sum(int(a.get("shares") or 0) for a in actual_actions)

        evolved_action, evolved_reason = _replay_evolved_buy_decision(entry, snap, cfg)
        hypo_shares = 0
        block_reason = ""
        deploy_ratio = None
        max_position_pct = None
        price = float(enriched.get(code, {}).get("price") or entry.get("price") or 0)

        if evolved_action == "buy":
            analysis = simulate_buy_analysis(pf, enriched, cfg, prefer_code=code)
            hypo_shares = int(analysis.get("buy_shares") or 0) if analysis.get("allowed") else 0
            block_reason = str(analysis.get("block_reason") or "")
            deploy_ratio = analysis.get("deploy_ratio")
            max_position_pct = analysis.get("max_position_pct")
            price = float(analysis.get("price") or price or 0)
            code = str(analysis.get("code") or code)
        elif actual_shares > 0 or str(entry.get("action") or "") == "buy":
            block_reason = evolved_reason[:120] if evolved_reason else "自进化未触发买入"

        if actual_shares <= 0 and hypo_shares <= 0 and not block_reason:
            if actual_actions or str(entry.get("action") or "") in ("buy", "sell"):
                pf = _advance_pf_with_actions(pf, entry.get("portfolio_actions") or [], enriched, cfg)
            continue

        target = row_accum.setdefault(
            code,
            {
                "code": code,
                "name": entry.get("name") or enriched.get(code, {}).get("name") or code,
                "actual_bought": 0,
                "hypothetical_bought": 0,
                "share_delta": 0,
                "price": price,
                "deploy_ratio": deploy_ratio,
                "max_position_pct": max_position_pct,
                "block_reason": block_reason,
            },
        )
        target["actual_bought"] = int(target.get("actual_bought") or 0) + actual_shares
        target["hypothetical_bought"] = int(target.get("hypothetical_bought") or 0) + hypo_shares
        target["share_delta"] = int(target["hypothetical_bought"]) - int(target["actual_bought"])
        if block_reason:
            target["block_reason"] = block_reason
        if deploy_ratio is not None:
            target["deploy_ratio"] = deploy_ratio
        if max_position_pct is not None:
            target["max_position_pct"] = max_position_pct
        if price > 0:
            target["price"] = price

        pf = _advance_pf_with_actions(pf, entry.get("portfolio_actions") or [], enriched, cfg)

    for code, shares in actual_buys.items():
        if code in row_accum:
            continue
        price = float(enriched.get(code, {}).get("price") or 0)
        row_accum[code] = {
            "code": code,
            "name": enriched.get(code, {}).get("name") or code,
            "actual_bought": shares,
            "hypothetical_bought": 0,
            "share_delta": -shares,
            "price": price,
            "block_reason": "无盘中买入信号记录",
        }

    rows = sorted(
        row_accum.values(),
        key=lambda r: (-int(r.get("actual_bought") or 0), str(r.get("code") or "")),
    )
    if not rows:
        return BuyRulesWhatIfResult(
            as_of=as_of,
            policy_note=_buy_policy_note(cfg),
            skipped=True,
            skip_reason="今日无买入相关标的",
        )

    prices = _buy_price_by_code(rows, enriched)
    actual_notional = _estimate_buy_notional(rows, shares_key="actual_bought", prices=prices)
    hypo_notional = _estimate_buy_notional(rows, shares_key="hypothetical_bought", prices=prices)
    return BuyRulesWhatIfResult(
        as_of=as_of,
        policy_note=_buy_policy_note(cfg),
        rows=rows,
        actual_buy_notional=actual_notional,
        hypothetical_buy_notional=hypo_notional,
        buy_notional_delta=round(hypo_notional - actual_notional, 2),
    )


def build_weekly_buy_rules_whatif(
    *,
    week_start: date,
    week_end: date,
    trades: list[dict[str, Any]],
    manifests: list[dict[str, Any]],
    settings: Optional[dict[str, Any]] = None,
) -> BuyRulesWhatIfResult:
    """Replay each trading day's buy signals vs ledger buys across the week."""
    from agent_reach.daily_run.settings import load_settings

    period_label = f"{week_start.isoformat()} ~ {week_end.isoformat()}"
    cfg = settings or load_settings()
    if not trades:
        return BuyRulesWhatIfResult(
            as_of=week_end.isoformat(),
            policy_note=_buy_policy_note(cfg),
            skipped=True,
            skip_reason="本周无成交记录，跳过买入基准值 vs 自进化规则对比",
            scope="weekly",
            period_label=period_label,
        )

    manifests_by_day: dict[str, list[dict[str, Any]]] = {}
    for record in manifests:
        day = str(record.get("_run_date") or "")
        if day:
            manifests_by_day.setdefault(day, []).append(record)

    daily_rows: list[dict[str, Any]] = []
    trading_days = 0
    actual_notional = 0.0
    hypo_notional = 0.0

    for day, day_trades in sorted(_trades_by_day(trades, week_start=week_start, week_end=week_end).items()):
        if not _day_has_buy(day_trades):
            continue
        day_manifests = manifests_by_day.get(day) or []
        baseline = _baseline_from_day_manifests(day_manifests)
        current = _close_from_day_manifests(day_manifests)
        if baseline is None or current is None:
            continue

        intraday = _intraday_from_day_manifests(day_manifests)
        day_summary = {
            "as_of": day,
            "trades": day_trades,
            "intraday_trades": intraday,
        }
        day_result = build_buy_rules_whatif(
            summary=day_summary,
            baseline=baseline,
            current=current,
            settings=cfg,
        )
        if day_result.skipped or not day_result.rows:
            continue
        trading_days += 1
        daily_rows.extend(day_result.rows)
        actual_notional += float(day_result.actual_buy_notional or 0)
        hypo_notional += float(day_result.hypothetical_buy_notional or 0)

    rows = _merge_weekly_buy_rows(daily_rows)
    if not rows:
        return BuyRulesWhatIfResult(
            as_of=week_end.isoformat(),
            policy_note=_buy_policy_note(cfg),
            skipped=True,
            skip_reason="本周无可用 manifest 基线，跳过买入基准值 vs 自进化规则对比",
            scope="weekly",
            period_label=period_label,
        )

    return BuyRulesWhatIfResult(
        as_of=week_end.isoformat(),
        policy_note=_buy_policy_note(cfg),
        rows=rows,
        actual_buy_notional=round(actual_notional, 2),
        hypothetical_buy_notional=round(hypo_notional, 2),
        buy_notional_delta=round(hypo_notional - actual_notional, 2),
        scope="weekly",
        period_label=period_label,
        trading_days=trading_days,
    )


def _realized_pnl_by_code(realized_sells: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in realized_sells:
        code = _normalize_code(str(row.get("code", "")))
        if not code:
            continue
        out[code] = out.get(code, 0.0) + float(row.get("realized_pnl") or 0)
    return out


def _policy_note(settings: dict[str, Any]) -> str:
    policy = deep_loss_policy(settings)
    deep_ratio = float(policy.get("sell_ratio", 1.0))
    non_deep_ratio = float(policy.get("non_deep_loss_sell_ratio", 1.0))
    cover_ratio = float(policy.get("cover_ratio", 1.0))
    return (
        f"深亏 sell_ratio **{deep_ratio:.0%}** · "
        f"非深亏 non_deep_loss_sell_ratio **{non_deep_ratio:.0%}** · "
        f"cover_ratio **{cover_ratio:.0%}**"
    )


def _estimate_hypothetical_realized(
    rows: list[dict[str, Any]],
    realized_by_code: dict[str, float],
) -> float:
    total = 0.0
    for row in rows:
        actual = int(row.get("actual_sold") or 0)
        hypo = int(row.get("hypothetical_sold") or 0)
        code = str(row.get("code") or "")
        actual_pnl = realized_by_code.get(code, 0.0)
        if actual > 0 and hypo > 0:
            total += actual_pnl * (hypo / actual)
        elif actual > 0 and hypo <= 0:
            continue
    return round(total, 2)


def _trades_by_day(
    trades: list[dict[str, Any]],
    *,
    week_start: date,
    week_end: date,
) -> dict[str, list[dict[str, Any]]]:
    by_day: dict[str, list[dict[str, Any]]] = {}
    for entry in trades:
        at = str(entry.get("at") or "")[:10]
        if not at:
            continue
        try:
            day = date.fromisoformat(at)
        except ValueError:
            continue
        if not (week_start <= day <= week_end):
            continue
        by_day.setdefault(at, []).append(entry)
    return by_day


def _day_has_sell(trades: list[dict[str, Any]]) -> bool:
    for entry in trades:
        for action in entry.get("actions") or []:
            if action.get("side") == "sell":
                return True
    return False


def _baseline_from_day_manifests(day_manifests: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    from agent_reach.daily_run.weekly_report import _manifest_sort_key, _snapshot_from_manifest

    for record in sorted(day_manifests, key=_manifest_sort_key):
        if record.get("job") != "morning":
            continue
        snap = _snapshot_from_manifest(record)
        if snap and (snap.get("portfolio") or {}).get("holdings"):
            return snap
    return None


def _close_from_day_manifests(day_manifests: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    from agent_reach.daily_run.weekly_report import _manifest_sort_key, _snapshot_from_manifest

    for record in sorted(day_manifests, key=_manifest_sort_key, reverse=True):
        if record.get("job") != "close":
            continue
        snap = _snapshot_from_manifest(record)
        if snap:
            return snap
    return None


def _intraday_from_day_manifests(day_manifests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from agent_reach.daily_run.weekly_report import _manifest_sort_key, _portfolio_summary_from_manifest

    for record in sorted(day_manifests, key=_manifest_sort_key, reverse=True):
        if record.get("job") != "close":
            continue
        ps = _portfolio_summary_from_manifest(record)
        if ps:
            intraday = list(ps.get("intraday_trades") or [])
            if intraday:
                return intraday
    return []


def _merge_weekly_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("code") or "")
        if not code:
            continue
        if code not in merged:
            merged[code] = {
                **row,
                "block_reasons": [row["block_reason"]] if row.get("block_reason") else [],
            }
            continue
        target = merged[code]
        target["actual_sold"] = int(target.get("actual_sold") or 0) + int(row.get("actual_sold") or 0)
        target["hypothetical_sold"] = int(target.get("hypothetical_sold") or 0) + int(
            row.get("hypothetical_sold") or 0
        )
        target["share_delta"] = int(target["hypothetical_sold"]) - int(target["actual_sold"])
        if row.get("block_reason"):
            target.setdefault("block_reasons", []).append(row["block_reason"])
    out: list[dict[str, Any]] = []
    for row in merged.values():
        reasons = [str(r) for r in row.pop("block_reasons", []) if r]
        if reasons:
            row["block_reason"] = reasons[0] if len(reasons) == 1 else "；".join(dict.fromkeys(reasons))
        out.append(row)
    out.sort(key=lambda r: (-int(r.get("actual_sold") or 0), str(r.get("code") or "")))
    return out


def build_weekly_sell_rules_whatif(
    *,
    week_start: date,
    week_end: date,
    trades: list[dict[str, Any]],
    manifests: list[dict[str, Any]],
    settings: Optional[dict[str, Any]] = None,
) -> SellRulesWhatIfResult:
    """Replay each trading day's morning holdings vs ledger sells across the week."""
    from agent_reach.daily_run.realized_pnl import compute_realized_pnl, replay_realized_sells
    from agent_reach.daily_run.settings import load_settings

    period_label = f"{week_start.isoformat()} ~ {week_end.isoformat()}"
    cfg = settings or load_settings()
    if not trades:
        return SellRulesWhatIfResult(
            as_of=week_end.isoformat(),
            policy_note=_policy_note(cfg),
            skipped=True,
            skip_reason="本周无成交记录，跳过基准值 vs 自进化规则对比",
            scope="weekly",
            period_label=period_label,
        )

    manifests_by_day: dict[str, list[dict[str, Any]]] = {}
    for record in manifests:
        day = str(record.get("_run_date") or "")
        if day:
            manifests_by_day.setdefault(day, []).append(record)

    daily_rows: list[dict[str, Any]] = []
    trading_days = 0
    actual_realized = 0.0
    hypo_realized = 0.0

    for day, day_trades in sorted(_trades_by_day(trades, week_start=week_start, week_end=week_end).items()):
        if not _day_has_sell(day_trades):
            continue
        day_manifests = manifests_by_day.get(day) or []
        baseline = _baseline_from_day_manifests(day_manifests)
        current = _close_from_day_manifests(day_manifests)
        if baseline is None or current is None:
            continue

        realized_sells = [r.to_dict() for r in replay_realized_sells(day_trades)]
        day_summary = {
            "as_of": day,
            "trades": day_trades,
            "realized_sells": realized_sells,
            "realized_pnl": compute_realized_pnl(day_trades),
        }
        day_result = build_sell_rules_whatif(
            summary=day_summary,
            baseline=baseline,
            current=current,
            settings=cfg,
        )
        if day_result.skipped or not day_result.rows:
            continue
        trading_days += 1
        daily_rows.extend(day_result.rows)
        actual_realized += float(day_result.actual_realized_pnl or 0)
        hypo_realized += float(day_result.hypothetical_realized_pnl or 0)

    rows = _merge_weekly_rows(daily_rows)
    if not rows:
        return SellRulesWhatIfResult(
            as_of=week_end.isoformat(),
            policy_note=_policy_note(cfg),
            skipped=True,
            skip_reason="本周无可用 manifest 基线，跳过基准值 vs 自进化规则对比",
            scope="weekly",
            period_label=period_label,
        )

    return SellRulesWhatIfResult(
        as_of=week_end.isoformat(),
        policy_note=_policy_note(cfg),
        rows=rows,
        actual_realized_pnl=round(actual_realized, 2),
        hypothetical_realized_pnl=round(hypo_realized, 2),
        realized_pnl_delta=round(hypo_realized - actual_realized, 2),
        scope="weekly",
        period_label=period_label,
        trading_days=trading_days,
    )


def build_sell_rules_whatif(
    *,
    summary: dict[str, Any],
    baseline: dict[str, Any],
    current: dict[str, Any],
    settings: Optional[dict[str, Any]] = None,
) -> SellRulesWhatIfResult:
    """Replay morning holdings through current sell-ratio rules vs ledger sells."""
    from agent_reach.daily_run.settings import load_settings

    data = summary
    as_of = str(data.get("as_of") or "")
    morning_pf = _morning_portfolio(baseline)
    morning_holdings = list(morning_pf.get("holdings") or [])
    if not morning_holdings:
        return SellRulesWhatIfResult(
            as_of=as_of,
            policy_note="",
            skipped=True,
            skip_reason="早盘无持仓基线，跳过基准值 vs 自进化规则对比",
        )

    cfg = settings or load_settings()
    enriched = build_enriched_symbols(current, cfg)
    actual_sells = _aggregate_actual_sells(data)
    realized_by_code = _realized_pnl_by_code(list(data.get("realized_sells") or []))
    actual_realized = float(data.get("realized_pnl") or 0)

    rows: list[dict[str, Any]] = []
    for holding in morning_holdings:
        code = _normalize_code(str(holding.get("code", "")))
        if not code:
            continue
        morning_shares = int(holding.get("shares") or 0)
        if morning_shares <= 0:
            continue

        row_holding = dict(holding)
        enriched_row = enriched.get(code, {})
        if enriched_row:
            row_holding.update({k: v for k, v in enriched_row.items() if k != "shares"})
        row_holding["shares"] = morning_shares
        analysis = deep_loss_sell_analysis(morning_pf, row_holding, enriched, cfg)
        hypothetical = int(analysis.get("sell_shares") or 0) if analysis.get("allowed") else 0
        actual = int(actual_sells.get(code, 0))

        if actual <= 0 and hypothetical <= 0 and not analysis.get("block_reason"):
            continue

        rows.append(
            {
                "code": code,
                "name": holding.get("name") or code,
                "morning_shares": morning_shares,
                "is_deep_loss": bool(analysis.get("is_deep_loss")),
                "sell_ratio": float(analysis.get("sell_ratio") or 0),
                "actual_sold": actual,
                "hypothetical_sold": hypothetical,
                "share_delta": hypothetical - actual,
                "block_reason": analysis.get("block_reason"),
            }
        )

    rows.sort(key=lambda r: (-int(r.get("actual_sold") or 0), str(r.get("code") or "")))

    if not rows:
        return SellRulesWhatIfResult(
            as_of=as_of,
            policy_note=_policy_note(cfg),
            skipped=True,
            skip_reason="今日无卖出相关标的",
        )

    hypo_realized = _estimate_hypothetical_realized(rows, realized_by_code)
    return SellRulesWhatIfResult(
        as_of=as_of,
        policy_note=_policy_note(cfg),
        rows=rows,
        actual_realized_pnl=round(actual_realized, 2),
        hypothetical_realized_pnl=hypo_realized,
        realized_pnl_delta=round(hypo_realized - actual_realized, 2),
    )


def render_sell_rules_whatif_markdown(result: SellRulesWhatIfResult | dict[str, Any]) -> str:
    """Markdown table: baseline sells vs harness-evolved sell-ratio replay."""
    data = result.to_dict() if isinstance(result, SellRulesWhatIfResult) else result
    scope = str(data.get("scope") or "daily")
    is_weekly = scope == "weekly"
    if data.get("skipped"):
        reason = str(data.get("skip_reason") or "无可对比数据")
        return f"## 🔀 卖出规则对比（基准值 vs 自进化规则）\n\n- {reason}"

    lines: list[str] = [
        "## 🔀 卖出规则对比（基准值 vs 自进化规则）",
        "",
        f"- 自进化规则：{data.get('policy_note') or '—'}",
    ]
    if is_weekly and data.get("period_label"):
        days = int(data.get("trading_days") or 0)
        day_s = f"，覆盖 **{days}** 个卖出交易日" if days else ""
        lines.append(f"- 统计周期：**{data['period_label']}**{day_s}")
    lines.extend(["", "| 标的 |" + ("" if is_weekly else " 早盘持仓 |") + " 基准值卖出 | 自进化卖出 | 差异 | 说明 |"])
    lines.append("| --- |" + ("" if is_weekly else " ---: |") + " ---: | ---: | ---: | --- |")

    for row in data.get("rows") or []:
        name = row.get("name") or row.get("code") or "?"
        code = row.get("code") or "?"
        morning = int(row.get("morning_shares") or 0)
        actual = int(row.get("actual_sold") or 0)
        hypo = int(row.get("hypothetical_sold") or 0)
        delta = int(row.get("share_delta") or 0)
        delta_s = f"{delta:+d}" if delta else "0"

        note_parts: list[str] = []
        if row.get("is_deep_loss"):
            ratio = row.get("sell_ratio")
            if ratio is not None:
                note_parts.append(f"深亏 {float(ratio):.0%}")
        elif row.get("sell_ratio") is not None and float(row.get("sell_ratio") or 1) < 0.999:
            note_parts.append(f"非深亏 {float(row['sell_ratio']):.0%}")
        block = str(row.get("block_reason") or "").strip()
        if block:
            note_parts.append(block)
        note = " · ".join(note_parts) if note_parts else "—"

        morning_col = f" {morning} |" if not is_weekly else ""
        lines.append(
            f"| **{name}** ({code}) |{morning_col} {actual} | {hypo} | {delta_s} | {note} |"
        )

    actual_pnl = data.get("actual_realized_pnl")
    hypo_pnl = data.get("hypothetical_realized_pnl")
    pnl_delta = data.get("realized_pnl_delta")
    if actual_pnl is not None and hypo_pnl is not None:
        lines.append("")
        sign_a = "+" if float(actual_pnl) >= 0 else ""
        sign_h = "+" if float(hypo_pnl) >= 0 else ""
        pnl_scope = "本周" if is_weekly else ""
        lines.append(
            f"- {pnl_scope}已实现盈亏（FIFO）：基准值 **{sign_a}¥{float(actual_pnl):,.0f}** → "
            f"自进化 **{sign_h}¥{float(hypo_pnl):,.0f}**"
        )
        if pnl_delta is not None and abs(float(pnl_delta)) >= 0.01:
            sign_d = "+" if float(pnl_delta) >= 0 else ""
            lines.append(f"- 自进化差异 **{sign_d}¥{float(pnl_delta):,.0f}**（仅含已成交标的按比例估算）")

    return "\n".join(lines).strip()


def render_buy_rules_whatif_markdown(result: BuyRulesWhatIfResult | dict[str, Any]) -> str:
    """Markdown table: baseline buys vs harness-evolved buy replay."""
    data = result.to_dict() if isinstance(result, BuyRulesWhatIfResult) else result
    scope = str(data.get("scope") or "daily")
    is_weekly = scope == "weekly"
    if data.get("skipped"):
        reason = str(data.get("skip_reason") or "无可对比数据")
        return f"## 🔀 买入规则对比（基准值 vs 自进化规则）\n\n- {reason}"

    lines: list[str] = [
        "## 🔀 买入规则对比（基准值 vs 自进化规则）",
        "",
        f"- 自进化规则：{data.get('policy_note') or '—'}",
    ]
    if is_weekly and data.get("period_label"):
        days = int(data.get("trading_days") or 0)
        day_s = f"，覆盖 **{days}** 个买入交易日" if days else ""
        lines.append(f"- 统计周期：**{data['period_label']}**{day_s}")
    lines.extend(["", "| 标的 | 基准值买入 | 自进化买入 | 差异 | 说明 |"])
    lines.append("| --- | ---: | ---: | ---: | --- |")

    for row in data.get("rows") or []:
        name = row.get("name") or row.get("code") or "?"
        code = row.get("code") or "?"
        actual = int(row.get("actual_bought") or 0)
        hypo = int(row.get("hypothetical_bought") or 0)
        delta = int(row.get("share_delta") or 0)
        delta_s = f"{delta:+d}" if delta else "0"

        note_parts: list[str] = []
        deploy_ratio = row.get("deploy_ratio")
        max_position_pct = row.get("max_position_pct")
        if deploy_ratio is not None:
            note_parts.append(f"deploy {float(deploy_ratio):.0%}")
        if max_position_pct is not None:
            note_parts.append(f"max_pos {float(max_position_pct):.0f}%")
        block = str(row.get("block_reason") or "").strip()
        if block:
            note_parts.append(block)
        note = " · ".join(note_parts) if note_parts else "—"

        lines.append(f"| **{name}** ({code}) | {actual} | {hypo} | {delta_s} | {note} |")

    actual_notional = data.get("actual_buy_notional")
    hypo_notional = data.get("hypothetical_buy_notional")
    notional_delta = data.get("buy_notional_delta")
    if actual_notional is not None and hypo_notional is not None:
        lines.append("")
        scope_s = "本周" if is_weekly else ""
        lines.append(
            f"- {scope_s}买入成交额估算：基准值 **¥{float(actual_notional):,.0f}** → "
            f"自进化 **¥{float(hypo_notional):,.0f}**"
        )
        if notional_delta is not None and abs(float(notional_delta)) >= 0.01:
            sign_d = "+" if float(notional_delta) >= 0 else ""
            lines.append(f"- 自进化差异 **{sign_d}¥{float(notional_delta):,.0f}**（按收盘价估算成交额）")

    return "\n".join(lines).strip()


def render_trade_rules_whatif_markdown(
    *,
    sell: SellRulesWhatIfResult | dict[str, Any] | None = None,
    buy: BuyRulesWhatIfResult | dict[str, Any] | None = None,
    intraday: IntradayFrictionWhatIfResult | dict[str, Any] | None = None,
    intraday_sell: IntradaySellWhatIfResult | dict[str, Any] | None = None,
) -> str:
    """Render sell, buy, intraday friction, and intraday sell what-if sections."""
    parts: list[str] = []
    if sell is not None:
        sell_md = render_sell_rules_whatif_markdown(sell)
        if sell_md.strip():
            parts.append(sell_md)
    if buy is not None:
        buy_md = render_buy_rules_whatif_markdown(buy)
        if buy_md.strip():
            parts.append(buy_md)
    if intraday_sell is not None:
        sell_scan_md = render_intraday_sell_whatif_markdown(intraday_sell)
        if sell_scan_md.strip():
            parts.append(sell_scan_md)
    if intraday is not None:
        intraday_md = render_intraday_friction_whatif_markdown(intraday)
        if intraday_md.strip():
            parts.append(intraday_md)
    return "\n\n".join(parts).strip()


def summarize_whatif_for_harness(
    whatif: dict[str, Any] | SellRulesWhatIfResult,
    *,
    weekly_pnl: Optional[float] = None,
    weekly_pnl_pct: Optional[float] = None,
) -> dict[str, Any]:
    """Turn baseline vs evolved sell comparison into harness memory/policy/playbook/plan."""
    data = whatif.to_dict() if isinstance(whatif, SellRulesWhatIfResult) else dict(whatif or {})
    empty: dict[str, Any] = {
        "memory": [],
        "policy": [],
        "playbook": [],
        "plan": [],
        "summary": "what-if skipped",
    }
    if data.get("skipped"):
        empty["summary"] = str(data.get("skip_reason") or "what-if skipped")
        return empty

    rows = list(data.get("rows") or [])
    actual_pnl = float(data.get("actual_realized_pnl") or 0)
    hypo_pnl = float(data.get("hypothetical_realized_pnl") or 0)
    pnl_delta = float(data.get("realized_pnl_delta") or 0)
    if not rows and abs(actual_pnl) < 0.01 and abs(hypo_pnl) < 0.01:
        empty["summary"] = "what-if no rows"
        return empty

    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    period = str(data.get("period_label") or data.get("as_of") or "").strip()
    scope = "weekly" if data.get("scope") == "weekly" else "daily"
    scope_s = "本周" if scope == "weekly" else "当日"

    memory.append(
        f"卖出规则 what-if（{period or scope_s}）："
        f"基准已实现 {actual_pnl:+,.0f} → 自进化 {hypo_pnl:+,.0f}（差 {pnl_delta:+,.0f}）"
    )
    if weekly_pnl is not None:
        sign = "+" if float(weekly_pnl) >= 0 else ""
        pct_s = f"（{float(weekly_pnl_pct):+.2f}%）" if weekly_pnl_pct is not None else ""
        memory.append(f"{scope_s}组合净值 {sign}¥{float(weekly_pnl):,.0f}{pct_s}")

    oversold_rows = [r for r in rows if int(r.get("share_delta") or 0) < 0]
    if oversold_rows:
        bits = []
        for row in oversold_rows[:4]:
            name = row.get("name") or row.get("code") or "?"
            bits.append(
                f"{name} 基准{int(row.get('actual_sold') or 0)}→自进化{int(row.get('hypothetical_sold') or 0)}"
            )
        memory.append(f"基准超额卖出 {len(oversold_rows)} 只：{'；'.join(bits)}")

    pnl_threshold = 200.0
    baseline_better = pnl_delta <= -pnl_threshold
    evolved_better = pnl_delta >= pnl_threshold
    full_clear_ok = baseline_better and (
        pnl_delta <= -500
        or any(abs(int(r.get("share_delta") or 0)) >= 500 for r in oversold_rows)
    )

    if baseline_better:
        if full_clear_ok:
            policy.append("基准优于自进化：调升 sell_ratio，条件允许允许全清")
            plan.append(
                "weekly：step-up sell_ratio / non_deep_loss_sell_ratio harness，"
                "满足条件时可上调至全清(1.0)"
            )
        else:
            policy.append("基准优于自进化：调升 sell_ratio 进化上界")
            plan.append(
                "weekly：step-up sell_ratio / non_deep_loss_sell_ratio harness"
            )
        playbook.append(
            f"{scope_s} what-if 基准已实现更高（{actual_pnl:+,.0f} vs {hypo_pnl:+,.0f}），"
            + (
                "harness 可上调至全清(1.0)"
                if full_clear_ok
                else "harness 适度上调 partial sell 比例"
            )
        )
    elif evolved_better:
        policy.append("自进化优于基准：维持 partial sell_ratio harness 进化")
        playbook.append(
            f"{scope_s} what-if 自进化已实现更优（{hypo_pnl:+,.0f} vs {actual_pnl:+,.0f}），"
            "保留 partial 减仓纪律"
        )
        plan.append("weekly：维持或略收紧 sell_ratio harness，避免回归基准全卖")

    for row in rows:
        actual = int(row.get("actual_sold") or 0)
        hypo = int(row.get("hypothetical_sold") or 0)
        block = str(row.get("block_reason") or "").strip()
        if actual > 0 and hypo < actual and block:
            name = row.get("name") or row.get("code") or "?"
            playbook.append(f"{name}：自进化阻断（{block[:48]}）但基准已卖 {actual} 股")

    summary = (
        f"what-if {scope} delta={pnl_delta:+.0f} "
        f"baseline_better={baseline_better} evolved_better={evolved_better}"
    )
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def summarize_buy_whatif_for_harness(
    whatif: dict[str, Any] | BuyRulesWhatIfResult,
    *,
    weekly_pnl: Optional[float] = None,
    weekly_pnl_pct: Optional[float] = None,
) -> dict[str, Any]:
    """Turn baseline vs evolved buy comparison into harness memory/policy/playbook/plan."""
    data = whatif.to_dict() if isinstance(whatif, BuyRulesWhatIfResult) else dict(whatif or {})
    empty: dict[str, Any] = {
        "memory": [],
        "policy": [],
        "playbook": [],
        "plan": [],
        "summary": "buy what-if skipped",
    }
    if data.get("skipped"):
        empty["summary"] = str(data.get("skip_reason") or "buy what-if skipped")
        return empty

    rows = list(data.get("rows") or [])
    actual_notional = float(data.get("actual_buy_notional") or 0)
    hypo_notional = float(data.get("hypothetical_buy_notional") or 0)
    notional_delta = float(data.get("buy_notional_delta") or 0)
    if not rows and abs(actual_notional) < 0.01 and abs(hypo_notional) < 0.01:
        empty["summary"] = "buy what-if no rows"
        return empty

    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    period = str(data.get("period_label") or data.get("as_of") or "").strip()
    scope = "weekly" if data.get("scope") == "weekly" else "daily"
    scope_s = "本周" if scope == "weekly" else "当日"

    memory.append(
        f"买入规则 what-if（{period or scope_s}）："
        f"基准成交额 ¥{actual_notional:,.0f} → 自进化 ¥{hypo_notional:,.0f}（差 {notional_delta:+,.0f}）"
    )
    if weekly_pnl is not None:
        sign = "+" if float(weekly_pnl) >= 0 else ""
        pct_s = f"（{float(weekly_pnl_pct):+.2f}%）" if weekly_pnl_pct is not None else ""
        memory.append(f"{scope_s}组合净值 {sign}¥{float(weekly_pnl):,.0f}{pct_s}")

    underbought_rows = [r for r in rows if int(r.get("share_delta") or 0) < 0]
    if underbought_rows:
        bits = []
        for row in underbought_rows[:4]:
            name = row.get("name") or row.get("code") or "?"
            bits.append(
                f"{name} 基准{int(row.get('actual_bought') or 0)}→自进化{int(row.get('hypothetical_bought') or 0)}"
            )
        memory.append(f"自进化少买 {len(underbought_rows)} 只：{'；'.join(bits)}")

    notional_threshold = 5000.0
    baseline_better = notional_delta <= -notional_threshold
    evolved_better = notional_delta >= notional_threshold

    if baseline_better:
        policy.append("基准买入优于自进化：上调 deploy_ratio harness")
        playbook.append(
            f"{scope_s} 买入 what-if 基准成交额更高（¥{actual_notional:,.0f} vs ¥{hypo_notional:,.0f}），"
            "harness 适度上调 deploy_ratio / max_position_pct"
        )
        plan.append("weekly：step-up deploy_ratio / max_position_pct harness")
    elif evolved_better:
        policy.append("自进化买入优于基准：维持 deploy_ratio harness 进化")
        playbook.append(
            f"{scope_s} 买入 what-if 自进化成交额更优（¥{hypo_notional:,.0f} vs ¥{actual_notional:,.0f}），"
            "保留买入 sizing 纪律"
        )
        plan.append("weekly：维持或略收紧 deploy_ratio harness")

    for row in rows:
        actual = int(row.get("actual_bought") or 0)
        hypo = int(row.get("hypothetical_bought") or 0)
        block = str(row.get("block_reason") or "").strip()
        if actual > 0 and hypo < actual and block:
            name = row.get("name") or row.get("code") or "?"
            playbook.append(f"{name}：自进化阻断（{block[:48]}）但基准已买 {actual} 股")

    summary = (
        f"buy what-if {scope} delta={notional_delta:+.0f} "
        f"baseline_better={baseline_better} evolved_better={evolved_better}"
    )
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


@dataclass
class IntradayFrictionWhatIfResult:
    as_of: str
    policy_note: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    friction_blocked_actual: int = 0
    friction_would_pass: int = 0
    trend_mismatch: int = 0
    actual_buy_count: int = 0
    evolved_buy_count: int = 0
    skipped: bool = False
    skip_reason: str = ""
    scope: str = "daily"
    period_label: str = ""
    trading_days: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "policy_note": self.policy_note,
            "rows": self.rows,
            "friction_blocked_actual": self.friction_blocked_actual,
            "friction_would_pass": self.friction_would_pass,
            "trend_mismatch": self.trend_mismatch,
            "actual_buy_count": self.actual_buy_count,
            "evolved_buy_count": self.evolved_buy_count,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "scope": self.scope,
            "period_label": self.period_label,
            "trading_days": self.trading_days,
        }


def _intraday_friction_policy_note(settings: dict[str, Any]) -> str:
    from agent_reach.daily_run.harness_policy import runtime_float_default, trend_policy_default

    friction = runtime_float_default(settings, "trading", "friction_min_return_pct")
    trend_pts = trend_policy_default(settings, "trend_min_points")
    trend_delta = trend_policy_default(settings, "trend_delta_threshold")
    return (
        f"friction_min_return_pct **{float(friction):.3f}** · "
        f"trend_min_points **{float(trend_pts):.0f}** · "
        f"trend_delta_threshold **{float(trend_delta):.1f}**"
    )


def _replay_evolved_trade_decision(
    entry: dict[str, Any],
    snapshot: dict[str, Any],
    settings: dict[str, Any],
):
    from agent_reach.daily_run.intraday import _decide_trade
    from agent_reach.daily_run.verdict import VerdictResult

    lookback_mss = float(entry.get("lookback_mss") or 0)
    trend = str(entry.get("trend") or "flat")
    mss_final = float(entry.get("mss_final") or lookback_mss)
    reasoning = str(entry.get("reasoning") or "")
    verdict_label = str(entry.get("verdict") or "观察")
    tag_blocked = "标签" in reasoning and "阻断买入" in reasoning

    verdict = VerdictResult(
        verdict=verdict_label,
        confidence="",
        mss_final=mss_final,
        entry_price=None,
        stop_loss_price=None,
        invalidation="",
        reasoning=reasoning,
        blocked=tag_blocked,
    )
    report = {
        "code": entry.get("code"),
        "name": entry.get("name"),
        "verdict": verdict_label,
        "mss_final": mss_final,
        "blocked": tag_blocked,
        "reasoning": reasoning,
    }
    snap = dict(snapshot)
    snap["code"] = entry.get("code")
    snap["name"] = entry.get("name")
    return _decide_trade(
        lookback_mss=lookback_mss,
        trend=trend,
        verdict=verdict,
        report=report,
        snapshot=snap,
        settings=settings,
        trade_index=1,
        expected_return_pct=entry.get("expected_return_pct"),
    )


def build_intraday_friction_whatif(
    *,
    summary: dict[str, Any],
    baseline: dict[str, Any],
    current: dict[str, Any],
    intraday_trades: Optional[list[dict[str, Any]]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> IntradayFrictionWhatIfResult:
    """Replay intraday scans: friction/trend blocks vs evolved rules."""
    from agent_reach.daily_run.settings import load_settings

    as_of = str(summary.get("as_of") or "")
    cfg = settings or load_settings()
    intraday_list = list(
        intraday_trades if intraday_trades is not None else summary.get("intraday_trades") or []
    )
    if not intraday_list:
        return IntradayFrictionWhatIfResult(
            as_of=as_of,
            policy_note=_intraday_friction_policy_note(cfg),
            skipped=True,
            skip_reason="今日无盘中扫描记录，跳过摩擦/趋势 what-if",
        )

    morning_pf = _morning_portfolio(baseline)
    pf = dict(morning_pf)
    pf.setdefault("watchlist", list(morning_pf.get("watchlist") or baseline.get("watchlist") or []))
    enriched = build_enriched_symbols(current, cfg)

    rows: list[dict[str, Any]] = []
    friction_blocked_actual = 0
    friction_would_pass = 0
    trend_mismatch = 0
    actual_buy_count = 0
    evolved_buy_count = 0

    for entry in intraday_list:
        code = _normalize_code(str(entry.get("code") or ""))
        if not code:
            continue
        snap = dict(current)
        snap["portfolio"] = pf
        snap["code"] = code
        snap["name"] = entry.get("name") or code

        decision = _replay_evolved_trade_decision(entry, snap, cfg)
        actual_action = str(entry.get("action") or "hold")
        actual_friction = bool(entry.get("friction_blocked"))
        evolved_action = str(decision.action or "hold")
        evolved_friction = bool(decision.friction_blocked)

        if actual_action == "buy":
            actual_buy_count += 1
        if evolved_action == "buy" and not decision.blocked and not evolved_friction:
            evolved_buy_count += 1

        if actual_friction:
            friction_blocked_actual += 1
        would_pass = actual_friction and evolved_action == "buy" and not evolved_friction and not decision.blocked
        if would_pass:
            friction_would_pass += 1

        trend = str(entry.get("trend") or "")
        if actual_action in ("hold", "skip") and evolved_action == "buy" and trend in ("mixed", "flat"):
            trend_mismatch += 1

        diverged = (
            actual_friction != evolved_friction
            or actual_action != evolved_action
            or would_pass
        )
        if not diverged:
            pf = _advance_pf_with_actions(pf, entry.get("portfolio_actions") or [], enriched, cfg)
            continue

        rows.append(
            {
                "code": code,
                "name": entry.get("name") or enriched.get(code, {}).get("name") or code,
                "scan_id": entry.get("scan_id") or entry.get("trade_id"),
                "lookback_mss": entry.get("lookback_mss"),
                "trend": trend,
                "actual_action": actual_action,
                "evolved_action": evolved_action,
                "actual_friction_blocked": actual_friction,
                "evolved_friction_blocked": evolved_friction,
                "block_reason": str(decision.reasoning or "")[:120],
            }
        )
        pf = _advance_pf_with_actions(pf, entry.get("portfolio_actions") or [], enriched, cfg)

    if not rows:
        return IntradayFrictionWhatIfResult(
            as_of=as_of,
            policy_note=_intraday_friction_policy_note(cfg),
            skipped=True,
            skip_reason="盘中扫描与自进化规则一致，无摩擦/趋势差异",
            friction_blocked_actual=friction_blocked_actual,
            actual_buy_count=actual_buy_count,
            evolved_buy_count=evolved_buy_count,
        )

    return IntradayFrictionWhatIfResult(
        as_of=as_of,
        policy_note=_intraday_friction_policy_note(cfg),
        rows=rows,
        friction_blocked_actual=friction_blocked_actual,
        friction_would_pass=friction_would_pass,
        trend_mismatch=trend_mismatch,
        actual_buy_count=actual_buy_count,
        evolved_buy_count=evolved_buy_count,
    )


def _merge_weekly_intraday_friction_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("code") or "")
        if not code:
            continue
        if code not in merged:
            merged[code] = {**row, "divergence_days": 1}
            continue
        target = merged[code]
        target["divergence_days"] = int(target.get("divergence_days") or 1) + 1
        if row.get("actual_friction_blocked"):
            target["actual_friction_blocked"] = True
        if row.get("evolved_friction_blocked"):
            target["evolved_friction_blocked"] = True
        block = str(row.get("block_reason") or "").strip()
        if block and block not in str(target.get("block_reason") or ""):
            prev = str(target.get("block_reason") or "").strip()
            target["block_reason"] = block if not prev else f"{prev}；{block}"[:120]
    out = list(merged.values())
    out.sort(key=lambda r: (-int(r.get("divergence_days") or 0), str(r.get("code") or "")))
    return out


def _intraday_baseline_from_day_manifests(day_manifests: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    baseline = _baseline_from_day_manifests(day_manifests)
    if baseline is not None:
        return baseline
    from agent_reach.daily_run.weekly_report import _manifest_sort_key, _snapshot_from_manifest

    for record in sorted(day_manifests, key=_manifest_sort_key):
        if record.get("job") != "morning":
            continue
        snap = _snapshot_from_manifest(record)
        if snap and snap.get("portfolio"):
            return snap
    return None


def build_weekly_intraday_friction_whatif(
    *,
    week_start: date,
    week_end: date,
    manifests: list[dict[str, Any]],
    settings: Optional[dict[str, Any]] = None,
) -> IntradayFrictionWhatIfResult:
    """Replay each trading day's intraday scans vs evolved friction/trend rules."""
    from agent_reach.daily_run.settings import load_settings

    period_label = f"{week_start.isoformat()} ~ {week_end.isoformat()}"
    cfg = settings or load_settings()

    manifests_by_day: dict[str, list[dict[str, Any]]] = {}
    for record in manifests:
        day = str(record.get("_run_date") or "")
        if day:
            manifests_by_day.setdefault(day, []).append(record)

    daily_rows: list[dict[str, Any]] = []
    trading_days = 0
    friction_blocked_actual = 0
    friction_would_pass = 0
    trend_mismatch = 0
    actual_buy_count = 0
    evolved_buy_count = 0

    for day in sorted(manifests_by_day.keys()):
        try:
            day_date = date.fromisoformat(day)
        except ValueError:
            continue
        if not (week_start <= day_date <= week_end):
            continue
        day_manifests = manifests_by_day[day]
        intraday = _intraday_from_day_manifests(day_manifests)
        if not intraday:
            continue
        baseline = _intraday_baseline_from_day_manifests(day_manifests)
        current = _close_from_day_manifests(day_manifests)
        if baseline is None or current is None:
            continue

        day_result = build_intraday_friction_whatif(
            summary={"as_of": day, "intraday_trades": intraday},
            baseline=baseline,
            current=current,
            settings=cfg,
        )
        if day_result.skipped or not day_result.rows:
            continue
        trading_days += 1
        daily_rows.extend(day_result.rows)
        friction_blocked_actual += day_result.friction_blocked_actual
        friction_would_pass += day_result.friction_would_pass
        trend_mismatch += day_result.trend_mismatch
        actual_buy_count += day_result.actual_buy_count
        evolved_buy_count += day_result.evolved_buy_count

    rows = _merge_weekly_intraday_friction_rows(daily_rows)
    if not rows:
        return IntradayFrictionWhatIfResult(
            as_of=week_end.isoformat(),
            policy_note=_intraday_friction_policy_note(cfg),
            skipped=True,
            skip_reason="本周无盘中摩擦/趋势差异，跳过基准值 vs 自进化规则对比",
            scope="weekly",
            period_label=period_label,
        )

    return IntradayFrictionWhatIfResult(
        as_of=week_end.isoformat(),
        policy_note=_intraday_friction_policy_note(cfg),
        rows=rows,
        friction_blocked_actual=friction_blocked_actual,
        friction_would_pass=friction_would_pass,
        trend_mismatch=trend_mismatch,
        actual_buy_count=actual_buy_count,
        evolved_buy_count=evolved_buy_count,
        scope="weekly",
        period_label=period_label,
        trading_days=trading_days,
    )


def render_intraday_friction_whatif_markdown(
    result: IntradayFrictionWhatIfResult | dict[str, Any],
) -> str:
    data = result.to_dict() if isinstance(result, IntradayFrictionWhatIfResult) else result
    scope = str(data.get("scope") or "daily")
    is_weekly = scope == "weekly"
    if data.get("skipped"):
        reason = str(data.get("skip_reason") or "无可对比数据")
        return f"## 🔀 盘中摩擦/趋势对比（基准值 vs 自进化规则）\n\n- {reason}"

    lines = [
        "## 🔀 盘中摩擦/趋势对比（基准值 vs 自进化规则）",
        "",
        f"- 自进化规则：{data.get('policy_note') or '—'}",
    ]
    if is_weekly and data.get("period_label"):
        days = int(data.get("trading_days") or 0)
        day_s = f"，覆盖 **{days}** 个盘中交易日" if days else ""
        lines.append(f"- 统计周期：**{data['period_label']}**{day_s}")
    lines.append(
        f"- 摩擦阻断 **{int(data.get('friction_blocked_actual') or 0)}** 次，"
        f"自进化可放行 **{int(data.get('friction_would_pass') or 0)}** 次 · "
        f"趋势误判 **{int(data.get('trend_mismatch') or 0)}** 次"
    )
    lines.extend(
        [
            "",
            "| 标的 | 基准动作 | 自进化 | 基准摩擦 | 自进化摩擦 | 说明 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in data.get("rows") or []:
        name = row.get("name") or row.get("code") or "?"
        code = row.get("code") or "?"
        note = str(row.get("block_reason") or "—")
        if is_weekly and int(row.get("divergence_days") or 0) > 1:
            note = f"{int(row['divergence_days'])}日差异 · {note}"
        lines.append(
            f"| **{name}** ({code}) | {row.get('actual_action') or '—'} | "
            f"{row.get('evolved_action') or '—'} | "
            f"{'是' if row.get('actual_friction_blocked') else '否'} | "
            f"{'是' if row.get('evolved_friction_blocked') else '否'} | "
            f"{note} |"
        )
    return "\n".join(lines).strip()


def summarize_intraday_friction_for_harness(
    whatif: dict[str, Any] | IntradayFrictionWhatIfResult,
) -> dict[str, Any]:
    data = whatif.to_dict() if isinstance(whatif, IntradayFrictionWhatIfResult) else dict(whatif or {})
    empty: dict[str, Any] = {
        "memory": [],
        "policy": [],
        "playbook": [],
        "plan": [],
        "summary": "intraday friction what-if skipped",
    }
    if data.get("skipped"):
        empty["summary"] = str(data.get("skip_reason") or "intraday friction what-if skipped")
        return empty

    friction_pass = int(data.get("friction_would_pass") or 0)
    trend_miss = int(data.get("trend_mismatch") or 0)
    memory = [
        (
            f"盘中摩擦 what-if：摩擦阻断 {int(data.get('friction_blocked_actual') or 0)} 次，"
            f"自进化可放行 {friction_pass} 次，趋势误判 {trend_miss} 次"
        )
    ]
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []
    if friction_pass >= 2:
        policy.append("摩擦成本过高：略降 friction_min_return_pct 或 exp_return 门槛")
        plan.append("intraday：验证 friction_min_return_pct 与落账成交对齐")
    if trend_miss >= 2:
        policy.append("趋势误判：mixed/flat 时收紧 buy_trends 或降低 trend_delta_threshold")
        plan.append("intraday：验证 trend_min_points / trend_delta_threshold")
    if friction_pass == 0 and trend_miss == 0:
        playbook.append("盘中摩擦/趋势纪律与自进化一致，维持当前门槛")

    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": f"intraday_friction pass={friction_pass} trend={trend_miss}",
    }


def _intraday_sell_actions(entry: dict[str, Any]) -> list[dict[str, Any]]:
    actions = [
        dict(a)
        for a in (entry.get("portfolio_actions") or [])
        if a.get("side") == "sell"
    ]
    if actions:
        return actions
    if entry.get("action") == "sell" and entry.get("shares") and entry.get("price"):
        return [
            {
                "side": "sell",
                "code": entry.get("code"),
                "name": entry.get("name"),
                "shares": entry.get("shares"),
                "price": entry.get("price"),
            }
        ]
    return []


def _holding_row(pf: dict[str, Any], code: str) -> Optional[dict[str, Any]]:
    norm = _normalize_code(code)
    for holding in pf.get("holdings") or []:
        if _normalize_code(str(holding.get("code", ""))) == norm:
            return dict(holding)
    return None


@dataclass
class IntradaySellWhatIfResult:
    as_of: str
    policy_note: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    actual_sell_shares: int = 0
    hypothetical_sell_shares: int = 0
    sell_share_delta: int = 0
    missed_sell_signals: int = 0
    skipped: bool = False
    skip_reason: str = ""
    scope: str = "daily"
    period_label: str = ""
    trading_days: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "policy_note": self.policy_note,
            "rows": self.rows,
            "actual_sell_shares": self.actual_sell_shares,
            "hypothetical_sell_shares": self.hypothetical_sell_shares,
            "sell_share_delta": self.sell_share_delta,
            "missed_sell_signals": self.missed_sell_signals,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "scope": self.scope,
            "period_label": self.period_label,
            "trading_days": self.trading_days,
        }


def build_intraday_sell_whatif(
    *,
    summary: dict[str, Any],
    baseline: dict[str, Any],
    current: dict[str, Any],
    intraday_trades: Optional[list[dict[str, Any]]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> IntradaySellWhatIfResult:
    """Replay intraday sell signals vs ledger sells under current harness rules."""
    from agent_reach.daily_run.portfolio_manager import deep_loss_sell_analysis
    from agent_reach.daily_run.settings import load_settings

    as_of = str(summary.get("as_of") or "")
    cfg = settings or load_settings()
    intraday_list = list(
        intraday_trades if intraday_trades is not None else summary.get("intraday_trades") or []
    )
    if not intraday_list:
        return IntradaySellWhatIfResult(
            as_of=as_of,
            policy_note=_policy_note(cfg),
            skipped=True,
            skip_reason="今日无盘中扫描记录，跳过卖出 scan replay",
        )

    morning_pf = _morning_portfolio(baseline)
    pf = dict(morning_pf)
    pf.setdefault("holdings", list(morning_pf.get("holdings") or []))
    enriched = build_enriched_symbols(current, cfg)

    rows: list[dict[str, Any]] = []
    actual_total = 0
    hypo_total = 0
    missed = 0

    for entry in intraday_list:
        code = _normalize_code(str(entry.get("code") or ""))
        if not code:
            continue
        holding = _holding_row(pf, code)
        if not holding or int(holding.get("shares") or 0) <= 0:
            pf = _advance_pf_with_actions(pf, entry.get("portfolio_actions") or [], enriched, cfg)
            continue

        snap = dict(current)
        snap["portfolio"] = pf
        snap["code"] = code
        snap["name"] = entry.get("name") or code

        actual_shares = sum(int(a.get("shares") or 0) for a in _intraday_sell_actions(entry))
        actual_action = str(entry.get("action") or "hold")

        decision = _replay_evolved_trade_decision(entry, snap, cfg)
        evolved_action = str(decision.action or "hold")
        hypo_shares = 0
        block_reason = ""
        sell_ratio = None
        is_deep_loss = False

        row_holding = dict(holding)
        enriched_row = enriched.get(code, {})
        if enriched_row:
            row_holding.update({k: v for k, v in enriched_row.items() if k != "shares"})
        row_holding["shares"] = int(holding.get("shares") or 0)

        if evolved_action == "sell":
            analysis = deep_loss_sell_analysis(pf, row_holding, enriched, cfg)
            hypo_shares = int(analysis.get("sell_shares") or 0) if analysis.get("allowed") else 0
            block_reason = str(analysis.get("block_reason") or decision.reasoning or "")[:120]
            sell_ratio = analysis.get("sell_ratio")
            is_deep_loss = bool(analysis.get("is_deep_loss"))
        elif actual_shares > 0:
            block_reason = str(decision.reasoning or "自进化未触发卖出")[:120]

        diverged = actual_shares != hypo_shares or (
            evolved_action == "sell" and actual_shares <= 0 and hypo_shares > 0
        )
        if evolved_action == "sell" and actual_shares <= 0 and hypo_shares > 0:
            missed += 1

        if not diverged and actual_shares <= 0 and hypo_shares <= 0:
            pf = _advance_pf_with_actions(pf, entry.get("portfolio_actions") or [], enriched, cfg)
            continue

        rows.append(
            {
                "code": code,
                "name": entry.get("name") or enriched.get(code, {}).get("name") or code,
                "scan_id": entry.get("scan_id") or entry.get("trade_id"),
                "actual_action": actual_action,
                "evolved_action": evolved_action,
                "actual_sold": actual_shares,
                "hypothetical_sold": hypo_shares,
                "share_delta": hypo_shares - actual_shares,
                "is_deep_loss": is_deep_loss,
                "sell_ratio": sell_ratio,
                "block_reason": block_reason,
            }
        )
        actual_total += actual_shares
        hypo_total += hypo_shares
        pf = _advance_pf_with_actions(pf, entry.get("portfolio_actions") or [], enriched, cfg)

    if not rows:
        return IntradaySellWhatIfResult(
            as_of=as_of,
            policy_note=_policy_note(cfg),
            skipped=True,
            skip_reason="盘中卖出信号与自进化规则一致，无 scan replay 差异",
            actual_sell_shares=actual_total,
            hypothetical_sell_shares=hypo_total,
        )

    return IntradaySellWhatIfResult(
        as_of=as_of,
        policy_note=_policy_note(cfg),
        rows=rows,
        actual_sell_shares=actual_total,
        hypothetical_sell_shares=hypo_total,
        sell_share_delta=hypo_total - actual_total,
        missed_sell_signals=missed,
    )


def _merge_weekly_intraday_sell_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("code") or "")
        if not code:
            continue
        if code not in merged:
            merged[code] = {**row, "divergence_days": 1}
            continue
        target = merged[code]
        target["divergence_days"] = int(target.get("divergence_days") or 1) + 1
        target["actual_sold"] = int(target.get("actual_sold") or 0) + int(row.get("actual_sold") or 0)
        target["hypothetical_sold"] = int(target.get("hypothetical_sold") or 0) + int(
            row.get("hypothetical_sold") or 0
        )
        target["share_delta"] = int(target["hypothetical_sold"]) - int(target["actual_sold"])
    out = list(merged.values())
    out.sort(key=lambda r: (-int(r.get("actual_sold") or 0), str(r.get("code") or "")))
    return out


def build_weekly_intraday_sell_whatif(
    *,
    week_start: date,
    week_end: date,
    manifests: list[dict[str, Any]],
    settings: Optional[dict[str, Any]] = None,
) -> IntradaySellWhatIfResult:
    """Replay each day's intraday sell scan vs ledger across the week."""
    from agent_reach.daily_run.settings import load_settings

    period_label = f"{week_start.isoformat()} ~ {week_end.isoformat()}"
    cfg = settings or load_settings()
    manifests_by_day: dict[str, list[dict[str, Any]]] = {}
    for record in manifests:
        day = str(record.get("_run_date") or "")
        if day:
            manifests_by_day.setdefault(day, []).append(record)

    daily_rows: list[dict[str, Any]] = []
    trading_days = 0
    actual_total = 0
    hypo_total = 0
    missed = 0

    for day in sorted(manifests_by_day.keys()):
        try:
            day_date = date.fromisoformat(day)
        except ValueError:
            continue
        if not (week_start <= day_date <= week_end):
            continue
        day_manifests = manifests_by_day[day]
        intraday = _intraday_from_day_manifests(day_manifests)
        if not intraday:
            continue
        baseline = _intraday_baseline_from_day_manifests(day_manifests)
        current = _close_from_day_manifests(day_manifests)
        if baseline is None or current is None:
            continue
        day_result = build_intraday_sell_whatif(
            summary={"as_of": day, "intraday_trades": intraday},
            baseline=baseline,
            current=current,
            settings=cfg,
        )
        if day_result.skipped or not day_result.rows:
            continue
        trading_days += 1
        daily_rows.extend(day_result.rows)
        actual_total += day_result.actual_sell_shares
        hypo_total += day_result.hypothetical_sell_shares
        missed += day_result.missed_sell_signals

    rows = _merge_weekly_intraday_sell_rows(daily_rows)
    if not rows:
        return IntradaySellWhatIfResult(
            as_of=week_end.isoformat(),
            policy_note=_policy_note(cfg),
            skipped=True,
            skip_reason="本周无盘中卖出 scan replay 差异",
            scope="weekly",
            period_label=period_label,
        )

    return IntradaySellWhatIfResult(
        as_of=week_end.isoformat(),
        policy_note=_policy_note(cfg),
        rows=rows,
        actual_sell_shares=actual_total,
        hypothetical_sell_shares=hypo_total,
        sell_share_delta=hypo_total - actual_total,
        missed_sell_signals=missed,
        scope="weekly",
        period_label=period_label,
        trading_days=trading_days,
    )


def render_intraday_sell_whatif_markdown(
    result: IntradaySellWhatIfResult | dict[str, Any],
) -> str:
    data = result.to_dict() if isinstance(result, IntradaySellWhatIfResult) else result
    scope = str(data.get("scope") or "daily")
    is_weekly = scope == "weekly"
    if data.get("skipped"):
        reason = str(data.get("skip_reason") or "无可对比数据")
        return f"## 🔀 盘中卖出 scan replay（基准值 vs 自进化规则）\n\n- {reason}"

    lines = [
        "## 🔀 盘中卖出 scan replay（基准值 vs 自进化规则）",
        "",
        f"- 自进化规则：{data.get('policy_note') or '—'}",
    ]
    if is_weekly and data.get("period_label"):
        days = int(data.get("trading_days") or 0)
        day_s = f"，覆盖 **{days}** 个盘中交易日" if days else ""
        lines.append(f"- 统计周期：**{data['period_label']}**{day_s}")
    lines.append(
        f"- 基准卖出 **{int(data.get('actual_sell_shares') or 0)}** 股 → "
        f"自进化 **{int(data.get('hypothetical_sell_shares') or 0)}** 股 · "
        f"错失信号 **{int(data.get('missed_sell_signals') or 0)}** 次"
    )
    lines.extend(
        [
            "",
            "| 标的 | 基准动作 | 自进化 | 基准卖出 | 自进化卖出 | 差异 | 说明 |",
            "| --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in data.get("rows") or []:
        name = row.get("name") or row.get("code") or "?"
        code = row.get("code") or "?"
        delta = int(row.get("share_delta") or 0)
        delta_s = f"{delta:+d}" if delta else "0"
        note = str(row.get("block_reason") or "—")
        if is_weekly and int(row.get("divergence_days") or 0) > 1:
            note = f"{int(row['divergence_days'])}日 · {note}"
        lines.append(
            f"| **{name}** ({code}) | {row.get('actual_action') or '—'} | "
            f"{row.get('evolved_action') or '—'} | {int(row.get('actual_sold') or 0)} | "
            f"{int(row.get('hypothetical_sold') or 0)} | {delta_s} | {note} |"
        )
    return "\n".join(lines).strip()


def summarize_intraday_sell_for_harness(
    whatif: dict[str, Any] | IntradaySellWhatIfResult,
) -> dict[str, Any]:
    data = whatif.to_dict() if isinstance(whatif, IntradaySellWhatIfResult) else dict(whatif or {})
    empty: dict[str, Any] = {
        "memory": [],
        "policy": [],
        "playbook": [],
        "plan": [],
        "summary": "intraday sell what-if skipped",
    }
    if data.get("skipped"):
        empty["summary"] = str(data.get("skip_reason") or "intraday sell what-if skipped")
        return empty

    missed = int(data.get("missed_sell_signals") or 0)
    delta = int(data.get("sell_share_delta") or 0)
    memory = [
        (
            f"盘中卖出 scan replay：基准 {int(data.get('actual_sell_shares') or 0)} 股 → "
            f"自进化 {int(data.get('hypothetical_sell_shares') or 0)} 股（差 {delta:+d}），"
            f"错失 {missed} 次"
        )
    ]
    policy: list[str] = []
    plan: list[str] = []
    playbook: list[str] = []
    if missed >= 2:
        policy.append("卖晚了：自进化防御/宏观卖出信号强于基准，可 step-up sell_ratio")
        plan.append("intraday：验证 defensive_trim 与 deep_loss sell_ratio 对齐")
    elif delta > 0:
        playbook.append("自进化卖出 scan 多于基准，维持 partial sell 纪律")
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": f"intraday_sell missed={missed} delta={delta:+d}",
    }

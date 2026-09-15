# -*- coding: utf-8
"""Seven-card Feishu layout for merged close review."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agent_reach.daily_run.report_push import ReportSection
from agent_reach.daily_run.snapshot_builder import _normalize_code
from agent_reach.daily_run.trade_calendar import today_shanghai

CLOSE_CARD_ORDER: tuple[str, ...] = (
    "close_summary",
    "holdings_ledger",
    "holdings_detail",
    "forecast_verify",
    "key_signals",
    "harness_evolution",
    "hot_research",
    "tomorrow_focus",
)

CLOSE_CARD_LABELS: dict[str, str] = {
    "close_summary": "📊 收盘摘要",
    "holdings_ledger": "📒 持仓台账",
    "holdings_detail": "📈 持仓详情",
    "forecast_verify": "🔮 预测验证",
    "key_signals": "⚠️ 关键信号",
    "harness_evolution": "🧬 Harness 自进化",
    "hot_research": "🔥 热点与调研",
    "tomorrow_focus": "📋 明日关注",
    "deepseek_interpretation": "🤖 DeepSeek 解读",
    "code_walk_interpretation": "🤖 走读 DeepSeek 解读",
    "decision_reflection": "🪞 决策反思",
    "risk_debate_interpretation": "⚖️ 三角风控辩论",
    "invest_debate_interpretation": "🐂🐻 多空辩论",
}


def close_card_layout_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    cfg = (settings or {}).get("report") or {}
    layout = str(cfg.get("close_card_layout", "six")).lower()
    return layout not in ("legacy", "old", "false", "0")


@dataclass
class CloseCardContext:
    portfolio_summary: dict[str, Any]
    symbol_rows: list[dict[str, Any]] = field(default_factory=list)
    verify_by_code: dict[str, dict[str, Any]] = field(default_factory=dict)
    forecast_review: Optional[dict[str, Any]] = None
    market_review: Optional[dict[str, Any]] = None
    macro_signals: Optional[dict[str, Any]] = None
    technical_scenarios: list[dict[str, Any]] = field(default_factory=list)
    research_results: list[dict[str, Any]] = field(default_factory=list)
    improvements: Optional[dict[str, Any]] = None
    narrative: Optional[dict[str, Any]] = None
    harness_result: Optional[dict[str, Any]] = None
    primary_snapshot: Optional[dict[str, Any]] = None
    settings: Optional[dict[str, Any]] = None
    watchlist_adjust_markdown: str = ""
    code_review_markdown: str = ""
    code_walk_narrative: Optional[dict[str, Any]] = None
    decision_reflection: Optional[dict[str, Any]] = None
    risk_debate_narrative: Optional[dict[str, Any]] = None
    invest_debate_narrative: Optional[dict[str, Any]] = None


def _fmt_pct(value: Any) -> str:
    """Format a value already in percent points (e.g. -0.43 → -0.43%)."""
    if value is None:
        return "—"
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{pct:+.2f}%"


def _fmt_money(value: Any, *, signed: bool = False) -> str:
    if value is None:
        return "—"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "—"
    if signed:
        sign = "+" if amount >= 0 else ""
        return f"{sign}¥{amount:,.0f}"
    return f"¥{amount:,.0f}"


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_price(value: Any) -> str:
    v = _optional_float(value)
    return f"¥{v:.2f}" if v is not None else "—"


def _fmt_weight_pct(value: Any) -> str:
    v = _optional_float(value)
    return f"{v:.1f}%" if v is not None else "—"


def collect_holdings_ledger_rows(
    portfolio_summary: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Actual holdings only (shares > 0), sorted by market value descending."""
    from agent_reach.daily_run.portfolio_manager import effective_days_held

    rows: list[dict[str, Any]] = []
    for raw in portfolio_summary.get("holdings") or []:
        if not isinstance(raw, dict):
            continue
        shares = int(raw.get("shares") or 0)
        if shares <= 0:
            continue
        code = _normalize_code(str(raw.get("code") or ""))
        if not code:
            continue
        close_price = _optional_float(raw.get("price") or raw.get("week_end_price") or raw.get("close_price"))
        market_value = _optional_float(raw.get("market_value"))
        if market_value is None and close_price is not None:
            market_value = round(shares * close_price, 2)
        weight = _optional_float(raw.get("weight_pct"))
        end_total = _optional_float(portfolio_summary.get("end_total"))
        if weight is None and end_total and market_value:
            weight = round(market_value / end_total * 100.0, 1)
        change_pct = _optional_float(raw.get("change_pct") or raw.get("week_chg_pct"))
        rows.append(
            {
                "code": code,
                "name": str(raw.get("name") or code),
                "shares": shares,
                "cost": _optional_float(raw.get("cost")),
                "close_price": close_price,
                "market_value": market_value,
                "weight_pct": weight,
                "change_pct": change_pct,
                "day_pnl": _optional_float(raw.get("day_pnl") or raw.get("week_chg")),
                "unrealized_pnl": _optional_float(raw.get("unrealized_pnl")),
                "unrealized_pct": _optional_float(raw.get("unrealized_pct")),
                "sector": str(raw.get("sector") or raw.get("industry") or "").strip() or None,
                "acquired_date": str(raw.get("acquired_date") or "").strip() or None,
                "days_held": effective_days_held(raw, settings=settings),
            }
        )
    rows.sort(key=lambda row: row.get("market_value") or 0, reverse=True)
    return rows


def _benchmark_vs_portfolio(
    portfolio_summary: dict[str, Any],
    market_review: Optional[dict[str, Any]],
    macro_signals: Optional[dict[str, Any]],
) -> str:
    port_pct = portfolio_summary.get("daily_pnl_pct")
    idx_pct: Optional[float] = None
    idx_name = "大盘"
    indices = (market_review or {}).get("indices") or {}
    for info in indices.values():
        if not isinstance(info, dict):
            continue
        if info.get("change_pct") is not None:
            idx_pct = float(info["change_pct"])
            idx_name = str(info.get("name") or idx_name)
            if "300" in idx_name or "沪深" in idx_name:
                break
    if idx_pct is None and macro_signals:
        raw = macro_signals.get("index_change_pct")
        if raw is not None:
            idx_pct = float(raw)
            idx_name = str(macro_signals.get("index_name") or "指数")
    if port_pct is None or idx_pct is None:
        return ""
    port = float(port_pct)
    idx = float(idx_pct)
    alpha = port - idx
    return f"组合 **{_fmt_pct(port)}** vs {idx_name} **{_fmt_pct(idx)}**（超额 **{alpha:+.2f}%**）"


def _risk_summary(
    portfolio_summary: dict[str, Any],
    technical_scenarios: list[dict[str, Any]],
) -> str:
    for line in portfolio_summary.get("reason_lines") or []:
        text = str(line).strip()
        if text:
            return text[:160]
    for note in portfolio_summary.get("notes") or []:
        text = str(note).strip()
        if text:
            return text[:160]
    for sc in technical_scenarios:
        scenario_type = str(sc.get("scenario_type") or "")
        name = sc.get("name") or sc.get("code") or "—"
        if scenario_type == "upper_shadow":
            return f"⚠️ {name} 长上影 setup，关注 {sc.get('session_low')} 支撑"
        if scenario_type == "liquidity_shrink":
            return f"⚠️ {name} 缩量回调，警惕流动性继续萎缩"
        if scenario_type == "min_cash_ratio_cap":
            cash = sc.get("setup_cash_ratio")
            if cash is not None:
                return f"⚠️ 现金仓位 {float(cash):.0%} 触达 min_cash 约束"
    deploy = portfolio_summary.get("deploy_budget_line")
    if deploy:
        return str(deploy)[:160]
    cash_ratio = portfolio_summary.get("cash_ratio")
    if cash_ratio is not None and float(cash_ratio) >= 0.45:
        return f"风控：现金 **{float(cash_ratio):.0%}**，维持防守配置"
    return "风控：按 MSS / macro_veto 纪律执行，无额外阻断"


def _collect_symbol_rows(
    symbol_results: list[dict[str, Any]],
    portfolio_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    holdings = {
        _normalize_code(str(h.get("code") or "")): h
        for h in (portfolio_summary.get("holdings") or [])
        if isinstance(h, dict)
    }
    watchlist = {
        _normalize_code(str(w.get("code") or "")): w
        for w in (portfolio_summary.get("watchlist") or [])
        if isinstance(w, dict)
    }

    for entry in symbol_results:
        inner = entry.get("result") or {}
        snap = inner.get("snapshot") or {}
        verify = inner.get("verify") or {}
        code = _normalize_code(str(snap.get("code") or entry.get("code") or ""))
        if not code or code in seen:
            continue
        seen.add(code)
        holding = holdings.get(code) or {}
        watch = watchlist.get(code) or {}
        shares = int(holding.get("shares") or 0)
        role = "持仓" if shares > 0 else "观察池"
        rows.append(
            {
                "code": code,
                "name": entry.get("name") or snap.get("name") or holding.get("name") or code,
                "price": holding.get("price") or snap.get("price") or verify.get("price_current"),
                "change_pct": holding.get("change_pct") if holding.get("change_pct") is not None else snap.get("change_pct"),
                "mss": snap.get("mss_final") or verify.get("mss_current"),
                "verdict": verify.get("verdict_current") or snap.get("verdict"),
                "shares": shares,
                "role": role,
                "sector": holding.get("sector") or watch.get("sector") or snap.get("sector"),
                "verify": verify,
                "snapshot": snap,
            }
        )

    for code, holding in holdings.items():
        if code in seen:
            continue
        seen.add(code)
        rows.append(
            {
                "code": code,
                "name": holding.get("name") or code,
                "price": holding.get("price"),
                "change_pct": holding.get("change_pct"),
                "mss": None,
                "verdict": "—",
                "shares": int(holding.get("shares") or 0),
                "role": "持仓",
                "sector": holding.get("sector"),
                "verify": {},
                "snapshot": {},
            }
        )
    for code, watch in watchlist.items():
        if code in seen:
            continue
        seen.add(code)
        rows.append(
            {
                "code": code,
                "name": watch.get("name") or code,
                "price": watch.get("price"),
                "change_pct": watch.get("change_pct"),
                "mss": None,
                "verdict": "—",
                "shares": 0,
                "role": "观察池",
                "sector": watch.get("sector"),
                "verify": {},
                "snapshot": {},
            }
        )
    return rows


def build_merged_close_card_context(
    *,
    symbol_results: list[dict[str, Any]],
    portfolio_summary: dict[str, Any],
    primary_snapshot: dict[str, Any],
    market_review: Optional[dict[str, Any]] = None,
    forecast_review: Optional[dict[str, Any]] = None,
    technical_watch: Optional[dict[str, Any]] = None,
    research_results: Optional[list[dict[str, Any]]] = None,
    improvements: Optional[dict[str, Any]] = None,
    narrative: Optional[dict[str, Any]] = None,
    harness_result: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> CloseCardContext:
    verify_by_code: dict[str, dict[str, Any]] = {}
    for entry in symbol_results:
        verify = (entry.get("result") or {}).get("verify") or {}
        code = _normalize_code(str(verify.get("code") or entry.get("code") or ""))
        if code:
            verify_by_code[code] = verify

    scenarios = list((technical_watch or {}).get("scenarios") or [])
    if not scenarios:
        scenarios = list((technical_watch or {}).get("registered") or [])

    return CloseCardContext(
        portfolio_summary=portfolio_summary,
        symbol_rows=_collect_symbol_rows(symbol_results, portfolio_summary),
        verify_by_code=verify_by_code,
        forecast_review=forecast_review,
        market_review=market_review,
        macro_signals=primary_snapshot.get("macro_signals"),
        technical_scenarios=scenarios,
        research_results=list(research_results or []),
        improvements=improvements,
        narrative=narrative,
        harness_result=harness_result,
        primary_snapshot=primary_snapshot,
        settings=settings,
    )


def build_single_close_card_context(
    run_result: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> CloseCardContext:
    snap = run_result.get("snapshot") or {}
    pf_summary = run_result.get("portfolio_summary") or {}
    verify = run_result.get("verify") or {}
    code = _normalize_code(str(verify.get("code") or snap.get("code") or ""))
    symbol_results = [
        {
            "code": code,
            "name": snap.get("name") or verify.get("name"),
            "result": run_result,
        }
    ]
    technical = run_result.get("technical_watch") or {}
    return CloseCardContext(
        portfolio_summary=pf_summary,
        symbol_rows=_collect_symbol_rows(symbol_results, pf_summary),
        verify_by_code={code: verify} if code else {},
        forecast_review=run_result.get("forecast_review"),
        market_review=run_result.get("market_review"),
        macro_signals=snap.get("macro_signals"),
        technical_scenarios=list(technical.get("scenarios") or []),
        research_results=list(run_result.get("research") or []),
        improvements=run_result.get("close_improvements"),
        narrative=run_result.get("llm_narrative"),
        harness_result=run_result.get("harness") or run_result.get("harness_result"),
        primary_snapshot=snap,
        settings=settings,
        watchlist_adjust_markdown=str(run_result.get("watchlist_adjust_markdown") or ""),
        code_review_markdown=str(run_result.get("code_review_markdown") or ""),
        code_walk_narrative=run_result.get("code_walk_narrative"),
        decision_reflection=run_result.get("decision_reflection"),
        risk_debate_narrative=run_result.get("risk_debate_narrative"),
        invest_debate_narrative=run_result.get("invest_debate_narrative"),
    )


def render_close_summary_markdown(ctx: CloseCardContext) -> str:
    pf = ctx.portfolio_summary
    lines: list[str] = []
    daily_pnl = pf.get("daily_pnl")
    if daily_pnl is not None:
        sign = "+" if float(daily_pnl) >= 0 else ""
        pct_s = _fmt_pct(pf.get("daily_pnl_pct"))
        lines.append(f"**当日盈亏：** {sign}¥{float(daily_pnl):,.0f}（{pct_s}）")
    elif pf.get("end_total") is not None:
        lines.append(f"**收盘净值：** ¥{float(pf['end_total']):,.0f}")

    bench = _benchmark_vs_portfolio(pf, ctx.market_review, ctx.macro_signals)
    if bench:
        lines.append(bench)

    if ctx.symbol_rows:
        lines.extend(["", "| 标的 | 代码 | 涨跌幅 | 角色 |", "|------|------|--------|------|"])
        for row in ctx.symbol_rows:
            lines.append(
                f"| {row.get('name')} | {row.get('code')} | {_fmt_pct(row.get('change_pct'))} "
                f"| {row.get('role')} |"
            )

    lines.extend(["", f"**风控：** {_risk_summary(pf, ctx.technical_scenarios)}"])
    return "\n".join(lines).strip()


def render_holdings_ledger_markdown_from_summary(
    portfolio_summary: dict[str, Any],
    *,
    as_of: str = "",
    change_col: str = "今日",
    pnl_col: str = "当日盈亏",
    total_label: str = "收盘净值",
    watchlist_hint: str = "见「持仓详情」卡，非本台账",
) -> str:
    pf = portfolio_summary or {}
    ledger_rows = collect_holdings_ledger_rows(pf)
    lines: list[str] = []
    if as_of:
        lines.append(f"- **{as_of}**")

    if not ledger_rows:
        lines.append("当前无持仓。")
    else:
        lines.extend(
            [
                "",
                f"| 标的 | 代码 | 股数 | 成本 | 收盘 | 市值 | 权重 | {change_col} | {pnl_col} | 浮盈 | 持有 |",
                "|------|------|------|------|------|------|------|------|----------|------|------|",
            ]
        )
        for row in ledger_rows:
            held = "—"
            if row.get("days_held") is not None:
                held = f"{int(row['days_held'])}天"
            elif row.get("acquired_date"):
                held = str(row["acquired_date"])
            lines.append(
                f"| {row.get('name')} | {row.get('code')} | {row.get('shares')} "
                f"| {_fmt_price(row.get('cost'))} | {_fmt_price(row.get('close_price'))} "
                f"| {_fmt_money(row.get('market_value'))} | {_fmt_weight_pct(row.get('weight_pct'))} "
                f"| {_fmt_pct(row.get('change_pct'))} | {_fmt_money(row.get('day_pnl'), signed=True)} "
                f"| {_fmt_money(row.get('unrealized_pnl'), signed=True)} | {held} |"
            )

    footer: list[str] = []
    stock_mv = _optional_float(pf.get("stock_mv"))
    cash = _optional_float(pf.get("cash"))
    end_total = _optional_float(pf.get("end_total"))
    cash_ratio = _optional_float(pf.get("cash_ratio"))
    total_unrealized = _optional_float(pf.get("total_unrealized"))
    watchlist_count = int(pf.get("watchlist_count") or 0)

    if stock_mv is not None:
        footer.append(f"**持仓市值** {_fmt_money(stock_mv)}（{len(ledger_rows)} 只）")
    if cash is not None:
        cash_part = f"**现金** {_fmt_money(cash)}"
        if cash_ratio is not None:
            cash_part += f"（{cash_ratio:.0%}）"
        footer.append(cash_part)
    if end_total is not None:
        footer.append(f"**{total_label}** {_fmt_money(end_total)}")
    if total_unrealized is not None and ledger_rows:
        footer.append(f"**累计浮盈** {_fmt_money(total_unrealized, signed=True)}")
    if watchlist_count > 0:
        footer.append(f"观察池 **{watchlist_count}** 只（{watchlist_hint}）")

    if footer:
        lines.extend(["", " · ".join(footer)])
    return "\n".join(line for line in lines if line is not None).strip()


def render_holdings_ledger_markdown(ctx: CloseCardContext) -> str:
    return render_holdings_ledger_markdown_from_summary(ctx.portfolio_summary or {})


def render_holdings_detail_markdown(ctx: CloseCardContext) -> str:
    if not ctx.symbol_rows:
        return ""
    lines = ["| 标的 | 收盘 | 涨跌 | MSS | 标签 | 股数 |", "|------|------|------|-----|------|------|"]
    for row in ctx.symbol_rows:
        price = row.get("price")
        price_s = f"¥{float(price):.2f}" if price is not None else "—"
        mss = row.get("mss")
        mss_s = f"{float(mss):.1f}" if mss is not None else "—"
        shares = int(row.get("shares") or 0)
        share_s = str(shares) if shares > 0 else "—"
        lines.append(
            f"| {row.get('name')} | {price_s} | {_fmt_pct(row.get('change_pct'))} | {mss_s} "
            f"| {row.get('verdict') or '—'} | {share_s} |"
        )
    return "\n".join(lines).strip()


def render_forecast_verify_markdown(ctx: CloseCardContext) -> str:
    forecast = ctx.forecast_review or {}
    evals = {str(e.get("code") or ""): e for e in (forecast.get("symbol_evals") or []) if isinstance(e, dict)}
    lines: list[str] = []

    structured_md = ""
    try:
        from datetime import date as date_cls

        from agent_reach.daily_run.forecast_tracking import (
            build_daily_structured_checks,
            render_daily_structured_checks_markdown,
        )
        from agent_reach.daily_run.week_forecast import load_active_forecast

        trading_date = today_shanghai()
        snap = ctx.primary_snapshot or {}
        if snap.get("_run_date"):
            trading_date = date_cls.fromisoformat(str(snap["_run_date"])[:10])
        active = load_active_forecast(trading_date)
        checks = build_daily_structured_checks(active, snap, trading_date=trading_date)
        from agent_reach.daily_run.forecast_tracking import build_kronos_divergence_day_checks

        checks.extend(build_kronos_divergence_day_checks(active, snap, trading_date=trading_date))
        structured_md = render_daily_structured_checks_markdown(checks)
    except Exception:
        structured_md = ""

    if structured_md:
        lines.append(structured_md)
        lines.append("")

    if forecast:
        total = int(forecast.get("symbol_total") or 0)
        hits = int(forecast.get("symbol_hits") or 0)
        acc = forecast.get("accuracy")
        acc_s = f"{float(acc):.0%}" if acc is not None else "—"
        lines.append(f"**周预测命中率：** {hits}/{total}（{acc_s}）")
        if forecast.get("mss_hit") is not None:
            mark = "✅" if forecast.get("mss_hit") else "❌"
            lines.append(
                f"**组合 MSS：** {mark} 预测 {forecast.get('mss_predicted')} "
                f"vs 实际 {forecast.get('mss_actual')}"
            )
        if forecast.get("optimization_notes"):
            lines.append(f"- 校准：{forecast['optimization_notes'][0][:100]}")
        lines.append("")

    lines.extend(
        [
            "| 标的 | 涨跌验证 | MSS Δ | 周预测 | 命中 |",
            "|------|----------|-------|--------|------|",
        ]
    )
    dir_cn = {"up": "↑", "down": "↓", "flat": "→"}
    for row in ctx.symbol_rows:
        code = str(row.get("code") or "")
        verify = row.get("verify") or ctx.verify_by_code.get(code) or {}
        price_delta = verify.get("price_delta_pct")
        price_s = _fmt_pct(price_delta) if price_delta is not None else "—"
        mss_delta = verify.get("mss_delta")
        mss_s = f"{float(mss_delta):+.0f}" if mss_delta is not None else "—"
        ev = evals.get(code) or {}
        if ev:
            pred = dir_cn.get(ev.get("predicted_direction"), "→")
            pred_range = ev.get("predicted_range")
            lo = hi = None
            if isinstance(pred_range, (list, tuple)) and len(pred_range) == 2:
                lo, hi = pred_range
            range_s = f"{pred}[{float(lo):+.1f},{float(hi):+.1f}%]" if lo is not None and hi is not None else pred
            actual = _fmt_pct(ev.get("actual_change_pct"))
            forecast_s = f"{range_s} / 实际 {actual}"
            hit_s = "✅" if ev.get("hit") else "❌"
        else:
            within = verify.get("mss_within_prediction")
            if within is True:
                forecast_s = "MSS 区间命中"
                hit_s = "✅"
            elif within is False:
                forecast_s = "MSS 区间偏离"
                hit_s = "❌"
            else:
                forecast_s = "—"
                hit_s = "—"
        lines.append(
            f"| {row.get('name')} | {price_s} | {mss_s} | {forecast_s} | {hit_s} |"
        )

    devs: list[str] = []
    for verify in ctx.verify_by_code.values():
        for dev in verify.get("deviations") or []:
            text = str(dev).strip()
            if text and text not in devs:
                devs.append(text[:100])
    if devs:
        lines.extend(["", "**偏差：**"])
        for dev in devs[:3]:
            lines.append(f"- {dev}")

    from agent_reach.daily_run.close_morning_handoff import render_morning_action_trace_markdown

    trace_md = render_morning_action_trace_markdown(ctx)
    if trace_md.strip():
        lines.extend(["", trace_md])

    from agent_reach.daily_run.midday_handoff import render_midday_close_loop_markdown

    loop_md = render_midday_close_loop_markdown(ctx, settings=ctx.settings)
    if loop_md.strip():
        lines.extend(["", loop_md])
    return "\n".join(lines).strip()


def _scenario_signal_line(sc: dict[str, Any]) -> str:
    scenario_type = str(sc.get("scenario_type") or "upper_shadow")
    name = sc.get("name") or sc.get("code") or "—"
    code = sc.get("code") or ""
    if scenario_type == "upper_shadow":
        low = sc.get("session_low")
        high = sc.get("session_high")
        return f"**{name}** 长上影 · 支撑 **{low}** / 压力 **{high}**"
    if scenario_type == "liquidity_shrink":
        return f"**{name}** 缩量回调 · 收 **{sc.get('session_close')}**"
    if scenario_type == "limit_up_shrink_pullback":
        return f"**{name} {code}** 涨停后缩量"
    if scenario_type == "mss_trend":
        return f"**{name}** MSS 走弱 · {sc.get('setup_mss_low')}~{sc.get('setup_mss_high')}"
    if scenario_type == "min_cash_ratio_cap":
        cash = sc.get("setup_cash_ratio")
        return f"**组合** min_cash 约束 · 现金 **{float(cash):.0%}**" if cash is not None else "**组合** min_cash 约束"
    return f"**{name}** {scenario_type}"


def render_key_signals_markdown(ctx: CloseCardContext) -> str:
    lines: list[str] = []
    if ctx.technical_scenarios:
        lines.append("**技术情景**")
        for sc in ctx.technical_scenarios[:6]:
            lines.append(f"- {_scenario_signal_line(sc)}")
            bear = (sc.get("bearish") or {}).get("label")
            bull = (sc.get("bullish") or {}).get("label")
            if bear:
                lines.append(f"  - 📉 {bear[:80]}")
            if bull:
                lines.append(f"  - 📈 {bull[:80]}")
        lines.append("")

    sectors = ctx.portfolio_summary.get("sector_weights") or []
    if sectors:
        parts = [
            f"**{s.get('sector') or '—'}** {float(s.get('weight_pct') or 0):.0f}%"
            for s in sectors[:3]
            if isinstance(s, dict)
        ]
        if parts:
            lines.append(f"**持仓板块：** {' · '.join(parts)}")

    sa = (ctx.market_review or {}).get("sector_analysis") or {}
    if sa.get("mainline_type"):
        lines.append(
            f"**板块主线：** {sa.get('mainline_type')} — {(sa.get('reasoning') or '')[:80]}"
        )

    cmp_ = (ctx.market_review or {}).get("comparison") or {}
    vs_y = cmp_.get("vs_yesterday") or {}
    if vs_y:
        from agent_reach.daily_run.systemic_risk import format_northbound_display

        north_delta = vs_y.get("northbound_delta_yi")
        if north_delta is not None:
            north_s = f"北向 {float(north_delta):+.1f} 亿"
        else:
            north_s = f"北向 {format_northbound_display(ctx.market_review.get('north') if ctx.market_review else None, emotion=(ctx.market_review or {}).get('emotion'))}"
        lines.append(
            f"**vs 昨日：** 涨停 {int(vs_y.get('limit_up_delta') or 0):+d} · "
            f"跌停 {int(vs_y.get('limit_down_delta') or 0):+d} · "
            f"{north_s}"
        )
    return "\n".join(lines).strip() or "暂无额外关键信号"


_POSITION_EVOLUTION_LABELS: dict[str, str] = {
    "deploy_ratio": "deploy_ratio",
    "max_position_pct": "max_position_pct",
}

_RUNTIME_EVOLUTION_LABELS: dict[str, str] = {
    "trade_min_scans": "最少扫描次数",
    "trade_every_n_scans": "交易间隔扫描",
    "max_applied_trades_per_day": "日最大成交笔数",
    "max_trade_evaluations_per_symbol": "单票最大评估次数",
    "max_holdings": "最大持仓数",
    "max_total_symbols": "最大标的数",
    "holding_lock_days": "锁仓天数",
    "stop_loss_ma20_pct": "MA20止损比例",
    "friction_min_return_pct": "摩擦最小收益",
}

_MSS_WEIGHT_LABELS: dict[str, str] = {
    "fx": "汇率",
    "flow": "资金流",
    "global": "全球",
    "sentiment": "舆情",
    "technical": "技术面",
    "quant": "量化",
    "risk": "风控",
}


def _overlay_param_label(section: str, key: str) -> str:
    from agent_reach.daily_run.harness_display import THRESHOLD_REF_SPECS

    if section == "threshold_overlay":
        return {spec[0]: spec[2] for spec in THRESHOLD_REF_SPECS}.get(key, key)
    if section == "position_overlay":
        return _POSITION_EVOLUTION_LABELS.get(key, key)
    if section == "runtime_overlay":
        return _RUNTIME_EVOLUTION_LABELS.get(key, key)
    if section == "mss_weights_overlay":
        return _MSS_WEIGHT_LABELS.get(key, key)
    return key


def _overlay_value_display(section: str, key: str, value: Any) -> str:
    from agent_reach.daily_run.harness_display import THRESHOLD_REF_SPECS, format_threshold_display

    if section == "threshold_overlay":
        fmt_by_key = {spec[0]: spec[3] for spec in THRESHOLD_REF_SPECS}
        return format_threshold_display(float(value), fmt_by_key.get(key, "float"))
    if section in ("position_overlay", "runtime_overlay"):
        val = float(value)
        if 0 <= val <= 1:
            return f"{val:.0%}"
        if val == int(val):
            return str(int(val))
        return f"{val:.2f}"
    if section == "mss_weights_overlay":
        return f"{float(value):.0%}"
    if isinstance(value, (list, tuple)):
        from agent_reach.daily_run.harness_display import format_lookback_weights_pct

        return format_lookback_weights_pct(list(value))
    return str(value)


def _match_harness_reason(param_label: str, param_key: str, reason_lines: list[str]) -> str:
    needles = [param_label, param_key]
    for line in reason_lines:
        text = str(line).strip()
        if not text:
            continue
        for needle in needles:
            if needle and needle in text:
                return text[:120]
    return ""


def _harness_tuning_reason_lines(
    *,
    portfolio_summary: dict[str, Any],
    harness_result: Optional[dict[str, Any]],
    settings: Optional[dict[str, Any]],
) -> tuple[list[str], str]:
    from agent_reach.daily_run.report_narrative import build_harness_tuning_summary

    ctx = {
        "job": "close",
        "portfolio_daily_pnl": portfolio_summary.get("daily_pnl"),
        "portfolio_daily_pnl_pct": portfolio_summary.get("daily_pnl_pct"),
        "sell_rules_whatif": portfolio_summary.get("sell_rules_whatif"),
        "buy_rules_whatif": portfolio_summary.get("buy_rules_whatif"),
        "intraday_friction_whatif": portfolio_summary.get("intraday_friction_whatif"),
        "intraday_sell_whatif": portfolio_summary.get("intraday_sell_whatif"),
        "harness_result": harness_result or {},
    }
    tuning = build_harness_tuning_summary(ctx, settings=settings) or {}
    lines: list[str] = []
    for bucket in ("policy_lines", "plan_lines", "playbook_lines", "execution_lines", "overlay_lines"):
        lines.extend(str(item).strip() for item in (tuning.get(bucket) or []) if str(item).strip())
    default_reason = str(tuning.get("summary") or "").strip()
    return lines, default_reason


def _session_harness_reason(harness_result: Optional[dict[str, Any]]) -> str:
    from agent_reach.daily_run.harness import _collect_harness_refinement_layers

    layers = _collect_harness_refinement_layers(harness_result or {})
    for _label, layer in reversed(layers):
        summary = str(layer.get("proposal_summary") or layer.get("reason") or "").strip()
        if summary:
            return summary[:120]
    if harness_result and harness_result.get("skipped"):
        return str(harness_result.get("reason") or harness_result.get("error") or "").strip()[:120]
    return ""


def collect_harness_evolution_rows(ctx: CloseCardContext) -> list[dict[str, str]]:
    """Build table rows: param / baseline / evolved / reason."""
    from agent_reach.daily_run.settings import effective_settings

    settings = ctx.settings or {}
    eff = effective_settings(settings)
    runtime = dict(eff.get("harness_runtime") or {})
    harness_result = ctx.harness_result or {}
    close_skills = harness_result.get("close_skills") or {}
    if isinstance(close_skills, dict):
        overlay = close_skills.get("effective_overlay") or {}
        for section, block in overlay.items():
            if block and not runtime.get(section):
                runtime[section] = block

    reason_lines, default_reason = _harness_tuning_reason_lines(
        portfolio_summary=ctx.portfolio_summary,
        harness_result=harness_result,
        settings=settings,
    )
    session_reason = _session_harness_reason(harness_result)
    fallback_reason = session_reason or default_reason or "收盘 harness 累积进化"

    rows: list[dict[str, str]] = []
    sections = (
        "threshold_overlay",
        "position_overlay",
        "runtime_overlay",
        "lookback_overlay",
        "mss_weights_overlay",
    )
    for section in sections:
        block = runtime.get(section) or {}
        if section == "lookback_overlay":
            lb = block.get("lookback_weights") if isinstance(block, dict) else block
            if not isinstance(lb, dict):
                continue
            base = lb.get("base")
            eff_w = lb.get("effective")
            if not base or not eff_w or list(base) == list(eff_w):
                continue
            label = "Lookback 权重"
            reason = _match_harness_reason(label, "lookback", reason_lines) or fallback_reason
            rows.append(
                {
                    "param": label,
                    "baseline": _overlay_value_display(section, "lookback_weights", base),
                    "evolved": _overlay_value_display(section, "lookback_weights", eff_w),
                    "reason": reason,
                }
            )
            continue
        if not isinstance(block, dict):
            continue
        for key, change in block.items():
            if not isinstance(change, dict):
                continue
            base = change.get("base")
            eff_val = change.get("effective")
            if base is None or eff_val is None:
                continue
            if isinstance(base, (int, float)) and isinstance(eff_val, (int, float)):
                if abs(float(eff_val) - float(base)) < 0.0001:
                    continue
            label = _overlay_param_label(section, str(key))
            reason = _match_harness_reason(label, str(key), reason_lines) or fallback_reason
            rows.append(
                {
                    "param": label,
                    "baseline": _overlay_value_display(section, str(key), base),
                    "evolved": _overlay_value_display(section, str(key), eff_val),
                    "reason": reason,
                }
            )

    trade_signals = runtime.get("trade_signals") or {}
    if isinstance(trade_signals, dict):
        active = [str(k) for k, v in trade_signals.items() if v]
        if active:
            rows.append(
                {
                    "param": "交易信号",
                    "baseline": "—",
                    "evolved": "、".join(active[:6]),
                    "reason": _match_harness_reason("交易信号", "trade_signals", reason_lines)
                    or fallback_reason,
                }
            )
    return rows


def render_harness_evolution_markdown(ctx: CloseCardContext) -> str:
    harness_result = ctx.harness_result or {}
    rows = collect_harness_evolution_rows(ctx)
    lines: list[str] = []

    if harness_result.get("skipped") and harness_result.get("error") and not rows:
        return f"Harness 跳过：{harness_result['error']}"

    rollback = harness_result.get("auto_rollback") or {}
    if rollback.get("triggered"):
        lines.append(
            f"⚠️ **坏交易回滚**：{rollback.get('pnl_label') or 'PnL'} "
            f"{rollback.get('pnl_pct')}% ≤ {rollback.get('threshold')}% · "
            f"已撤销 {rollback.get('count', 0)} 次 refine"
        )
        lines.append("")

    if rows:
        lines.extend(
            [
                "| 参数 | 原有 | 自进化 | 原因 |",
                "|------|------|--------|------|",
            ]
        )
        for row in rows[:12]:
            lines.append(
                f"| {row['param']} | {row['baseline']} | {row['evolved']} | {row['reason'][:80]} |"
            )
        return "\n".join(lines).strip()

    from agent_reach.daily_run.report_narrative import _compact_harness_execution_summary

    execution = _compact_harness_execution_summary(harness_result)
    if execution:
        lines.append("**本次精炼**")
        for item in execution[:4]:
            lines.append(f"- {item}")
        return "\n".join(lines).strip()

    return "今日无 harness 参数调整，维持当前有效值"


def _holding_codes(portfolio_summary: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for row in portfolio_summary.get("holdings") or []:
        if isinstance(row, dict):
            code = _normalize_code(str(row.get("code") or ""))
            if code:
                codes.add(code)
    return codes


def render_hot_research_markdown(ctx: CloseCardContext) -> str:
    holding_codes = _holding_codes(ctx.portfolio_summary)
    lines: list[str] = []
    snap = dict(ctx.primary_snapshot or {})
    snap["portfolio"] = {
        **((snap.get("portfolio") or {})),
        "holdings": ctx.portfolio_summary.get("holdings") or [],
        "watchlist": [],
    }

    from agent_reach.daily_run.symbol_news import render_symbol_news_markdown

    for row in ctx.symbol_rows:
        if row.get("role") != "持仓":
            continue
        code = str(row.get("code") or "")
        if code not in holding_codes:
            continue
        news = render_symbol_news_markdown(code, snap, name=str(row.get("name") or ""))
        if news:
            lines.append(news)
            lines.append("")

    macro = ctx.macro_signals or {}
    from agent_reach.daily_run.xueqiu_hot_display import (
        render_portfolio_hot_post_overlap_markdown,
        render_portfolio_hot_stock_overlap_markdown,
    )

    stock_matches = [
        m
        for m in (macro.get("portfolio_hot_stocks") or [])
        if _normalize_code(str(m.get("code") or "")) in holding_codes
    ]
    post_matches = macro.get("portfolio_hot_posts") or []
    stock_md = render_portfolio_hot_stock_overlap_markdown(stock_matches)
    post_md = render_portfolio_hot_post_overlap_markdown(post_matches)
    if stock_md:
        lines.extend(stock_md.splitlines())
        lines.append("")
    if post_md:
        lines.extend(post_md.splitlines())
        lines.append("")

    ok_research = [
        r
        for r in ctx.research_results
        if r.get("success") and (r.get("summary") or "").strip()
    ]
    if ok_research:
        lines.append("**🔍 Exa 调研（持仓）**")
        for row in ok_research[:4]:
            label = row.get("label") or "调研"
            summary = str(row.get("summary") or "").strip().splitlines()[0][:160]
            lines.append(f"- **{label}：** {summary}")
    return "\n".join(lines).strip() or "暂无与持仓直接相关的热点/调研"


def render_tomorrow_focus_markdown(ctx: CloseCardContext) -> str:
    from agent_reach.daily_run.close_morning_handoff import (
        collect_tomorrow_focus_items,
        format_tomorrow_focus_markdown,
    )

    body = format_tomorrow_focus_markdown(collect_tomorrow_focus_items(ctx))
    return body or "- 按 MSS 与 macro_veto 纪律执行，明日早盘再确认"


_CARD_RENDERERS = {
    "close_summary": render_close_summary_markdown,
    "holdings_ledger": render_holdings_ledger_markdown,
    "holdings_detail": render_holdings_detail_markdown,
    "forecast_verify": render_forecast_verify_markdown,
    "key_signals": render_key_signals_markdown,
    "harness_evolution": render_harness_evolution_markdown,
    "hot_research": render_hot_research_markdown,
    "tomorrow_focus": render_tomorrow_focus_markdown,
}


def render_close_card_sections(ctx: CloseCardContext) -> list[ReportSection]:
    sections: list[ReportSection] = []
    for category in CLOSE_CARD_ORDER:
        renderer = _CARD_RENDERERS[category]
        body = renderer(ctx)
        if not (body or "").strip():
            continue
        sections.append(ReportSection(category=category, title="", body=body.strip()))
    from agent_reach.daily_run.deepseek_interpretation_cards import (
        append_code_walk_interpretation_report_section,
        append_interpretation_report_section,
        append_job_interpretation_report_section,
        code_walk_interpretation_label,
        interpretation_card_label,
    )

    def _renumber(cards: list[ReportSection]) -> None:
        total = len(cards)
        for i, sec in enumerate(cards, start=1):
            if sec.category == "deepseek_interpretation":
                label = interpretation_card_label(ctx.narrative)
            elif sec.category == "code_walk_interpretation":
                label = code_walk_interpretation_label(ctx.code_walk_narrative)
            elif sec.category == "decision_reflection":
                label = CLOSE_CARD_LABELS.get("decision_reflection", sec.category)
            elif sec.category == "risk_debate_interpretation":
                label = CLOSE_CARD_LABELS.get("risk_debate_interpretation", sec.category)
            elif sec.category == "invest_debate_interpretation":
                label = CLOSE_CARD_LABELS.get("invest_debate_interpretation", sec.category)
            else:
                label = CLOSE_CARD_LABELS.get(sec.category, sec.category)
            sec.title = f"{label} {i}/{total}"

    sections = append_interpretation_report_section(
        sections,
        ctx.narrative,
        job="close",
        settings=ctx.settings,
    )
    if ctx.watchlist_adjust_markdown.strip():
        sections.append(
            ReportSection(
                category="watchlist_adjust",
                title="",
                body=ctx.watchlist_adjust_markdown.strip(),
            )
        )
    if ctx.code_review_markdown.strip():
        sections.append(
            ReportSection(
                category="code_review",
                title="",
                body=ctx.code_review_markdown.strip(),
            )
        )
    sections = append_code_walk_interpretation_report_section(
        sections,
        ctx.code_walk_narrative,
        settings=ctx.settings,
    )
    sections = append_job_interpretation_report_section(
        sections,
        ctx.decision_reflection,
        job="decision_reflection",
        category="decision_reflection",
        settings=ctx.settings,
    )
    sections = append_job_interpretation_report_section(
        sections,
        ctx.risk_debate_narrative,
        job="risk_debate",
        category="risk_debate_interpretation",
        settings=ctx.settings,
    )
    sections = append_job_interpretation_report_section(
        sections,
        ctx.invest_debate_narrative,
        job="invest_debate",
        category="invest_debate_interpretation",
        settings=ctx.settings,
    )
    _renumber(sections)
    return sections

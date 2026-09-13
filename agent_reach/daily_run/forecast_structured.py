# -*- coding: utf-8
"""Structured weekly forecast — numeric predictions, verification, operation plans."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Optional

from agent_reach.daily_run.snapshot_builder import _normalize_code
from agent_reach.daily_run.trade_calendar import today_shanghai
from agent_reach.daily_run.week_forecast import load_forecast, next_trading_week_range
from agent_reach.daily_run.forecast_content_scope import (
    build_forecast_content_scope,
    filter_sectors_to_holdings,
)
from agent_reach.daily_run.forecast_operation_matrix import (
    build_forecast_operation_matrix,
    render_master_operation_markdown,
    render_scenario_markdown,
    render_timeline_markdown,
)
from agent_reach.daily_run.forecast_quality import (
    audit_forecast_cross_check,
    confidence_tier_detail,
    enrich_market_prediction,
    enrich_symbol_prediction,
    load_cross_reference_data,
    position_hint_for_confidence,
)

_VAGUE_PATTERN = re.compile(
    r"(有望|可能|关注|谨慎|或许|大概|或|视情况|待定|择机|适度|灵活|偏|略|待观察)"
)

_FORECAST_SECTION_LABELS = (
    "上周验证",
    "操作总表",
    "情景预案",
    "大盘板块",
    "持仓预案",
    "关键事件",
)


def forecast_section_labels() -> tuple[str, ...]:
    return _FORECAST_SECTION_LABELS


def contains_vague_language(text: str) -> bool:
    return bool(_VAGUE_PATTERN.search(str(text or "")))


def sanitize_prediction_text(text: str) -> str:
    """Strip vague wording; caller should prefer numeric templates instead."""
    cleaned = _VAGUE_PATTERN.sub("", str(text or ""))
    return re.sub(r"\s{2,}", " ", cleaned).strip(" ，,;；")


def _fmt_pct(value: float, *, signed: bool = True) -> str:
    if signed:
        return f"{value:+.1f}%"
    return f"{value:.1f}%"


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _prior_trading_week_start(week_start: date) -> date:
    return week_start - timedelta(days=7)


def aggregate_symbol_week_prediction(sym: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Turn daily symbol paths into one verifiable week-level numeric prediction."""
    days = sym.get("days") or {}
    if not days:
        return None
    cum_lo = 0.0
    cum_hi = 0.0
    cum_mid = 0.0
    for ds in sorted(days.keys()):
        row = days[ds]
        lo, hi = row.get("change_pct_range") or [0, 0]
        cum_lo += float(lo)
        cum_hi += float(hi)
        cum_mid += float(row.get("expected_change_pct") or (float(lo) + float(hi)) / 2)
    base = _optional_float(sym.get("base_price")) or 0.0
    price_lo = round(base * (1 + cum_lo / 100), 2) if base > 0 else None
    price_hi = round(base * (1 + cum_hi / 100), 2) if base > 0 else None
    price_mid = round(base * (1 + cum_mid / 100), 2) if base > 0 else None
    name = str(sym.get("name") or sym.get("code") or "—")
    code = str(sym.get("code") or "")
    text = (
        f"{name}下周预测：区间 {price_lo:.0f}-{price_hi:.0f} 元，"
        f"中枢 {price_mid:.0f} 元，周涨跌幅 {_fmt_pct(cum_lo)} ~ {_fmt_pct(cum_hi)}"
        if price_lo is not None and price_hi is not None and price_mid is not None
        else f"{name}下周预测：周涨跌幅 {_fmt_pct(cum_lo)} ~ {_fmt_pct(cum_hi)}，中枢 {_fmt_pct(cum_mid)}"
    )
    return {
        "code": code,
        "name": name,
        "role": sym.get("role") or "",
        "base_price": base,
        "change_pct_low": round(cum_lo, 2),
        "change_pct_high": round(cum_hi, 2),
        "change_pct_mid": round(cum_mid, 2),
        "price_low": price_lo,
        "price_high": price_hi,
        "price_mid": price_mid,
        "text": sanitize_prediction_text(text),
    }


def build_market_prediction(
    *,
    mss_daily: dict[str, Any],
    calibration: dict[str, Any],
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Numeric HS300-style weekly return band derived from MSS drift + calibration."""
    cfg = (settings or {}).get("weekly_report") or {}
    index_name = str(cfg.get("benchmark_index_name") or "沪深300")
    medians = [float(r.get("median")) for r in mss_daily.values() if r.get("median") is not None]
    mss_delta = (medians[-1] - medians[0]) if len(medians) >= 2 else 0.0
    bias = float(calibration.get("bias_pct") or 0)
    vol = max(0.8, float(calibration.get("vol_scale") or 1.0))
    mid = round(mss_delta * 0.12 - bias * 0.25, 2)
    lo = round(mid - vol, 2)
    hi = round(mid + vol, 2)
    text = (
        f"下周大盘（{index_name}）预测：{_fmt_pct(lo)} ~ {_fmt_pct(hi)}，中枢 {_fmt_pct(mid)}"
    )
    return {
        "label": f"下周大盘（{index_name}）",
        "index_name": index_name,
        "change_pct_low": lo,
        "change_pct_high": hi,
        "change_pct_mid": mid,
        "text": sanitize_prediction_text(text),
    }


def build_sector_predictions(
    *,
    digest: Optional[dict[str, Any]] = None,
    snapshot: Optional[dict[str, Any]] = None,
    market_mid: float = 0.0,
    limit: int = 4,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    hot = list((digest or {}).get("hot_sectors") or [])
    if not hot and snapshot:
        sector = snapshot.get("industry") or snapshot.get("sector")
        if sector:
            hot = [{"sector": sector, "avg_change_pct": snapshot.get("change_pct") or 0}]
    for item in hot[:limit]:
        name = str(item.get("sector") or item.get("name") or "热点板块")
        chg = _optional_float(item.get("avg_change_pct") or item.get("change_pct")) or 0.0
        excess_mid = round(chg * 0.35 - market_mid * 0.15, 2)
        band = max(1.0, abs(chg) * 0.25 + 0.8)
        lo = round(excess_mid - band, 2)
        hi = round(excess_mid + band, 2)
        text = f"{name}下周预测：相对沪深300超额收益 {_fmt_pct(lo)} ~ {_fmt_pct(hi)}"
        rows.append(
            {
                "name": name,
                "excess_low": lo,
                "excess_high": hi,
                "excess_mid": excess_mid,
                "text": sanitize_prediction_text(text),
            }
        )
    return rows


def build_structured_predictions(
    forecast: dict[str, Any],
    *,
    portfolio: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
    digest: Optional[dict[str, Any]] = None,
    snapshot: Optional[dict[str, Any]] = None,
    enriched: Optional[dict[str, Any]] = None,
    outlook: Optional[dict[str, Any]] = None,
    watchlist_intel: Optional[dict[str, Any]] = None,
    risk_calendar: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    calibration = forecast.get("calibration_used") or {}
    snap = snapshot or forecast.get("_snapshot") or {}
    market_raw = build_market_prediction(
        mss_daily=forecast.get("mss_daily") or {},
        calibration=calibration,
        settings=settings,
    )
    market = enrich_market_prediction(
        market_raw,
        snapshot=snap,
        mss_daily=forecast.get("mss_daily") or {},
        calibration=calibration,
        settings=settings,
    )
    symbols: list[dict[str, Any]] = []
    kronos_paths = forecast.get("kronos_paths") or {}
    enriched_map = enriched or {}
    for code, sym in (forecast.get("symbols") or {}).items():
        role = str(sym.get("role") or "")
        if role not in ("holding", "watchlist"):
            continue
        row = aggregate_symbol_week_prediction({**sym, "code": code})
        if row:
            enriched_row = enrich_symbol_prediction(
                row,
                sym=sym,
                enriched=enriched_map.get(_normalize_code(code)) or enriched_map.get(code),
                kronos=kronos_paths.get(code) or sym.get("kronos"),
                settings=settings,
            )
            enriched_row["role"] = role
            symbols.append(enriched_row)
    pf = portfolio or {}
    if not symbols:
        for h in pf.get("holdings") or []:
            code = _normalize_code(str(h.get("code") or ""))
            sym = (forecast.get("symbols") or {}).get(code)
            if sym:
                row = aggregate_symbol_week_prediction({**sym, "code": code})
                if row:
                    enriched_row = enrich_symbol_prediction(
                        row,
                        sym=sym,
                        enriched=enriched_map.get(code),
                        kronos=kronos_paths.get(code) or sym.get("kronos"),
                        settings=settings,
                    )
                    enriched_row["role"] = sym.get("role") or "holding"
                    symbols.append(enriched_row)
    sectors_all = build_sector_predictions(
        digest=digest,
        snapshot=snap,
        market_mid=float(market.get("change_pct_mid") or 0),
    )
    sectors = filter_sectors_to_holdings(
        sectors_all,
        portfolio=pf,
        settings=settings,
    )
    cross_ref = load_cross_reference_data(portfolio=pf, settings=settings)
    ref_holdings = cross_ref.get("holdings") or {}
    for sym in symbols:
        code = _normalize_code(str(sym.get("code") or ""))
        ref_px = _optional_float((ref_holdings.get(code) or {}).get("close_price"))
        if ref_px is not None:
            sym["base_price"] = ref_px
    audit = audit_forecast_cross_check(
        {"market": market, "symbols": symbols, "sectors": sectors},
        cross_ref,
    )
    base = {
        "market": market,
        "sectors": sectors,
        "symbols": symbols,
        "generated_for_week": forecast.get("week_start"),
        "cross_reference": cross_ref,
        "cross_check": audit,
    }
    content_scope = build_forecast_content_scope(
        structured=base,
        forecast=forecast,
        portfolio=pf,
        settings=settings,
        digest=digest,
        outlook=outlook,
        snapshot=snap,
        enriched=enriched_map,
        watchlist_intel=watchlist_intel,
        risk_calendar=risk_calendar,
    )
    homogeneity: Optional[dict[str, Any]] = None
    try:
        from agent_reach.daily_run.forecast_consensus_monitor import build_homogeneity_warning

        homogeneity = build_homogeneity_warning(forecast, settings=settings)
    except Exception:
        homogeneity = None
    return {**base, "content_scope": content_scope, "homogeneity_warning": homogeneity}


def _weight_pct(holding: dict[str, Any], portfolio_total: Optional[float]) -> Optional[float]:
    from agent_reach.daily_run.forecast_operation_matrix import _holding_market_value, _portfolio_total

    total = portfolio_total
    if not total:
        total = _portfolio_total({"holdings": [holding]})
    if not total:
        return None
    mv = _holding_market_value(holding)
    return round(mv / float(total) * 100.0, 1)


def build_tied_operation_plans(
    structured: dict[str, Any],
    *,
    portfolio: Optional[dict[str, Any]] = None,
    outlook: Optional[dict[str, Any]] = None,
    master_rows: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """Bind numeric predictions to master-table operation rows for holdings card."""
    pf = portfolio or {}
    total = _optional_float(
        pf.get("total_value") or pf.get("portfolio_total") or pf.get("total")
    )
    if not total:
        from agent_reach.daily_run.forecast_operation_matrix import _portfolio_total

        total = _portfolio_total(pf) or None
    sym_preds = {str(s.get("code")): s for s in structured.get("symbols") or [] if s.get("code")}
    master_map = {
        _normalize_code(str(r.get("code") or "")): r
        for r in master_rows or []
        if r.get("code") and r.get("code") != "CASH"
    }
    plans: list[dict[str, Any]] = []
    for h in pf.get("holdings") or []:
        code = _normalize_code(str(h.get("code") or ""))
        if not code:
            continue
        pred = sym_preds.get(code) or {}
        cur = _weight_pct(h, total) or 0.0
        conf = _optional_float(pred.get("confidence_pct")) or 60.0
        pos_hint = str(pred.get("position_hint") or position_hint_for_confidence(conf))
        name = str(h.get("name") or pred.get("name") or code)
        pred_text = pred.get("text") or "—"
        master = master_map.get(code) or {}
        if master:
            op = master.get("operation") or "持有"
            trigger = master.get("trigger") or "—"
            target = master.get("target_weight") or f"维持{cur:.0f}%"
            stop = master.get("stop_loss") or "—"
            action = f"{op}：{trigger} → 目标 {target}；止损 {stop}"
        else:
            action = f"持有：维持 {cur:.0f}% 仓位；MSS<45 减至 {max(cur - 5, 5):.0f}%"
        plans.append(
            {
                "code": code,
                "name": name,
                "prediction_text": pred_text,
                "operation_plan": sanitize_prediction_text(action),
                "current_weight_pct": cur,
                "confidence_pct": conf,
                "position_hint": pos_hint,
                "role": "holding",
            }
        )

    held_codes = {
        _normalize_code(str(h.get("code") or ""))
        for h in pf.get("holdings") or []
        if h.get("code")
    }
    for w in pf.get("watchlist") or []:
        code = _normalize_code(str(w.get("code") or ""))
        if not code or code in held_codes:
            continue
        pred = sym_preds.get(code) or {}
        if not pred:
            continue
        conf = _optional_float(pred.get("confidence_pct")) or 55.0
        pos_hint = str(pred.get("position_hint") or position_hint_for_confidence(conf))
        name = str(w.get("name") or pred.get("name") or code)
        pred_text = pred.get("text") or "—"
        master = master_map.get(code) or {}
        if master:
            op = master.get("operation") or "新建仓"
            trigger = master.get("trigger") or "—"
            target = master.get("target_weight") or "0%→10%"
            stop = master.get("stop_loss") or "—"
            action = f"{op}：{trigger} → 目标 {target}；止损 {stop}"
        else:
            action = f"观察：触发条件见 outlook；置信度偏低时暂不新建仓"
        plans.append(
            {
                "code": code,
                "name": name,
                "prediction_text": pred_text,
                "operation_plan": sanitize_prediction_text(action),
                "current_weight_pct": 0.0,
                "confidence_pct": conf,
                "position_hint": pos_hint,
                "role": "watchlist",
            }
        )
    return plans[:16]


def _in_range(value: float, lo: float, hi: float) -> bool:
    return float(lo) <= float(value) <= float(hi)


def _verify_market_row(
    pred: dict[str, Any],
    actual_pct: Optional[float],
) -> dict[str, Any]:
    lo = float(pred.get("change_pct_low") or 0)
    hi = float(pred.get("change_pct_high") or 0)
    mid = float(pred.get("change_pct_mid") or (lo + hi) / 2)
    label = str(pred.get("label") or pred.get("text") or "大盘")
    if actual_pct is None:
        return {
            "prediction": f"{label} {_fmt_pct(lo)}~{_fmt_pct(hi)}",
            "actual": "—",
            "verify": "—",
            "deviation": "—",
            "hit": None,
            "reason": "",
        }
    hit = _in_range(actual_pct, lo, hi)
    dev = round(actual_pct - mid, 2)
    verify = f"✅ 命中区间" if hit else f"❌ 偏离区间"
    reason = "" if hit else f"实际 {_fmt_pct(actual_pct)} 超出预测 {_fmt_pct(lo)}~{_fmt_pct(hi)}"
    return {
        "prediction": f"{label} {_fmt_pct(lo)}~{_fmt_pct(hi)}",
        "actual": _fmt_pct(actual_pct),
        "verify": verify,
        "deviation": _fmt_pct(dev),
        "hit": hit,
        "reason": reason,
    }


def _verify_symbol_row(
    pred: dict[str, Any],
    *,
    week_close: Optional[float],
    week_low: Optional[float],
    week_change_pct: Optional[float],
) -> dict[str, Any]:
    name = str(pred.get("name") or pred.get("code") or "—")
    lo_p = _optional_float(pred.get("price_low"))
    hi_p = _optional_float(pred.get("price_high"))
    pred_s = (
        f"{name} {lo_p:.0f}-{hi_p:.0f}元"
        if lo_p is not None and hi_p is not None
        else f"{name} {_fmt_pct(float(pred.get('change_pct_low') or 0))}~{_fmt_pct(float(pred.get('change_pct_high') or 0))}"
    )
    if week_close is None and week_change_pct is None:
        return {
            "prediction": pred_s,
            "actual": "—",
            "verify": "—",
            "deviation": "—",
            "hit": None,
            "reason": "",
        }
    hit = False
    reason = ""
    if lo_p is not None and hi_p is not None and week_close is not None:
        hit = _in_range(week_close, lo_p, hi_p)
        if not hit and week_low is not None and week_low < lo_p:
            reason = f"{name} 跌破区间下沿（最低 {week_low:.0f} 元），原因：周内跌幅超预期"
        elif not hit and week_close > hi_p:
            reason = f"{name} 突破区间上沿（收盘 {week_close:.0f} 元），原因：动能强于预测"
        actual_s = f"{week_close:.0f}元" + (f"（最低{week_low:.0f}）" if week_low else "")
        mid_p = _optional_float(pred.get("price_mid")) or week_close
        dev = round((week_close - mid_p) / mid_p * 100, 2) if mid_p else 0.0
    else:
        lo_c = float(pred.get("change_pct_low") or 0)
        hi_c = float(pred.get("change_pct_high") or 0)
        act = float(week_change_pct or 0)
        hit = _in_range(act, lo_c, hi_c)
        actual_s = _fmt_pct(act)
        mid_c = float(pred.get("change_pct_mid") or (lo_c + hi_c) / 2)
        dev = round(act - mid_c, 2)
        if not hit:
            reason = f"{name} 涨跌幅 {actual_s} 超出预测区间"
    return {
        "prediction": pred_s,
        "actual": actual_s,
        "verify": "✅ 命中区间" if hit else "❌ 未命中",
        "deviation": _fmt_pct(dev),
        "hit": hit,
        "reason": reason,
    }


def _verify_sector_row(
    pred: dict[str, Any],
    actual_excess: Optional[float],
) -> dict[str, Any]:
    name = str(pred.get("name") or "板块")
    lo = float(pred.get("excess_low") or 0)
    hi = float(pred.get("excess_high") or 0)
    pred_s = f"{name} 超额 {_fmt_pct(lo)}~{_fmt_pct(hi)}"
    if actual_excess is None:
        return {
            "prediction": pred_s,
            "actual": "—",
            "verify": "—",
            "deviation": "—",
            "hit": None,
            "reason": "",
        }
    hit = _in_range(actual_excess, lo, hi)
    mid = float(pred.get("excess_mid") or (lo + hi) / 2)
    return {
        "prediction": pred_s,
        "actual": _fmt_pct(actual_excess),
        "verify": "✅ 命中区间" if hit else "❌ 未命中",
        "deviation": _fmt_pct(round(actual_excess - mid, 2)),
        "hit": hit,
        "reason": "" if hit else f"{name} 超额 {_fmt_pct(actual_excess)} 超出预测区间",
    }


def _symbol_week_actuals(
    pred: dict[str, Any],
    prior_forecast: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Return week close price, week low price, week change % from stored actuals."""
    code = str(pred.get("code") or "")
    base = _optional_float(pred.get("base_price")) or 0.0
    trading_days = list(prior_forecast.get("trading_days") or [])
    actuals = prior_forecast.get("actuals") or {}
    prices: list[float] = []
    cum = 0.0
    for ds in trading_days:
        sym_actual = (actuals.get(ds) or {}).get("symbols", {}).get(code) or {}
        close_px = _optional_float(sym_actual.get("close_price"))
        if close_px is not None:
            prices.append(close_px)
            if base > 0:
                cum = (close_px / base - 1) * 100
            continue
        chg = _optional_float(sym_actual.get("change_pct"))
        if chg is None:
            continue
        cum += chg
        if base > 0:
            prices.append(base * (1 + cum / 100))

    week_close: Optional[float] = None
    week_low: Optional[float] = None
    week_chg: Optional[float] = None

    if trading_days:
        try:
            from agent_reach.daily_run.prior_close import load_close_baseline

            last_day = date.fromisoformat(str(trading_days[-1]))
            baseline = load_close_baseline(code, target_day=last_day, settings=settings) or {}
            week_close = _optional_float(baseline.get("price"))
        except Exception:
            week_close = None

    if week_close is None and prices:
        week_close = prices[-1]
    if prices:
        week_low = min(prices)
    elif week_close is not None:
        week_low = week_close

    if week_close is not None and base > 0:
        week_chg = round((week_close / base - 1) * 100, 2)
    elif prices:
        week_chg = round(cum, 2)

    return week_close, week_low, week_chg


def verify_prior_week_predictions(
    prior_forecast: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Score last week's structured predictions against realized outcomes."""
    structured = prior_forecast.get("structured_predictions") or {}
    if not structured:
        structured = build_structured_predictions(prior_forecast, settings=settings)

    ws = date.fromisoformat(str(prior_forecast.get("week_start")))
    we = date.fromisoformat(str(prior_forecast.get("week_end")))
    from agent_reach.daily_run.weekly_card_metrics import fetch_benchmark_weekly_return

    bench = fetch_benchmark_weekly_return(ws, we, settings=settings)
    bench_pct = _optional_float(bench.get("return_pct"))

    rows: list[dict[str, Any]] = []
    market_row = _verify_market_row(structured.get("market") or {}, bench_pct)
    rows.append(market_row)

    for sym_pred in structured.get("symbols") or []:
        close_p, low_p, chg = _symbol_week_actuals(sym_pred, prior_forecast, settings=settings)
        rows.append(
            _verify_symbol_row(
                sym_pred,
                week_close=close_p,
                week_low=low_p,
                week_change_pct=chg,
            )
        )

    for sec_pred in structured.get("sectors") or []:
        excess = None
        if bench_pct is not None:
            chg = _optional_float(
                (prior_forecast.get("sector_actuals") or {}).get(sec_pred.get("name"))
            )
            if chg is not None:
                excess = round(chg - bench_pct, 2)
        rows.append(_verify_sector_row(sec_pred, excess))

    scored = [r for r in rows if r.get("hit") is not None]
    hits = sum(1 for r in scored if r.get("hit"))
    total = len(scored)
    accuracy_pct = round(hits / total * 100.0, 1) if total else None
    deviations = []
    for r in scored:
        dev_s = str(r.get("deviation") or "")
        if dev_s.endswith("%"):
            try:
                deviations.append(abs(float(dev_s.rstrip("%").replace("+", ""))))
            except ValueError:
                pass
    avg_dev = round(sum(deviations) / len(deviations), 2) if deviations else None

    result = {
        "week_start": prior_forecast.get("week_start"),
        "week_end": prior_forecast.get("week_end"),
        "rows": rows,
        "hits": hits,
        "total": total,
        "accuracy_pct": accuracy_pct,
        "avg_deviation_pct": avg_dev,
        "miss_reasons": [r["reason"] for r in rows if r.get("reason")],
    }
    try:
        from agent_reach.daily_run.forecast_tracking import enrich_week_verification_metrics

        return enrich_week_verification_metrics(result, prior_forecast, settings=settings)
    except Exception:
        return result


def four_week_accuracy_trend(
    *,
    as_of: Optional[date] = None,
    settings: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Load up to 4 prior forecast files and return weekly accuracy series."""
    d = as_of or today_shanghai()
    week_start, _ = next_trading_week_range(d)
    trend: list[dict[str, Any]] = []
    cursor = week_start
    for _ in range(4):
        prior_start = _prior_trading_week_start(cursor)
        prior = load_forecast(prior_start)
        if not prior:
            cursor = prior_start
            continue
        stored = prior.get("week_verification")
        if isinstance(stored, dict) and stored.get("accuracy_pct") is not None:
            acc = float(stored["accuracy_pct"])
        else:
            verified = verify_prior_week_predictions(prior, settings=settings)
            acc = verified.get("accuracy_pct")
            if acc is not None:
                prior["week_verification"] = verified
                try:
                    from agent_reach.daily_run.week_forecast import save_forecast

                    save_forecast(prior)
                except Exception:
                    pass
        if acc is not None:
            trend.append(
                {
                    "week_start": prior.get("week_start"),
                    "week_end": prior.get("week_end"),
                    "accuracy_pct": acc,
                }
            )
        cursor = prior_start
    trend.reverse()
    return trend


def ensure_structured_forecast_payload(
    forecast: dict[str, Any],
    *,
    portfolio: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
    persist_prior: bool = False,
) -> dict[str, Any]:
    """Build structured sections on demand (render path / tests without full workflow)."""
    if forecast.get("structured_predictions"):
        return forecast
    pf = portfolio or forecast.get("portfolio_snapshot") or forecast.get("_portfolio")
    if pf is None:
        holdings = [
            {"code": code, "name": sym.get("name") or code}
            for code, sym in (forecast.get("symbols") or {}).items()
            if sym.get("role") == "holding"
        ]
        if holdings:
            pf = {"holdings": holdings, "total_value": 100000.0}
    return attach_structured_forecast(
        forecast,
        portfolio=pf,
        settings=settings,
        persist_prior=persist_prior,
    )


def attach_structured_forecast(
    forecast: dict[str, Any],
    *,
    portfolio: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
    digest: Optional[dict[str, Any]] = None,
    outlook: Optional[dict[str, Any]] = None,
    persist_prior: bool = True,
) -> dict[str, Any]:
    """Populate structured_predictions, operation_plans, prior_week_verification on forecast dict."""
    data = dict(forecast)
    snap = data.get("_snapshot") or {}
    enriched_map: dict[str, Any] = {}
    if snap:
        try:
            from agent_reach.daily_run.symbols import build_enriched_symbols

            enriched_map = build_enriched_symbols(snap)
        except Exception:
            enriched_map = {}
    structured = build_structured_predictions(
        data,
        portfolio=portfolio,
        settings=settings,
        digest=digest,
        snapshot=snap,
        enriched=enriched_map,
        outlook=outlook,
        watchlist_intel=data.get("watchlist_intel") or snap.get("watchlist_intel"),
        risk_calendar=list((outlook or {}).get("risk_calendar") or []),
    )
    data["structured_predictions"] = structured
    data["forecast_quality_audit"] = structured.get("cross_check") or {}
    matrix = build_forecast_operation_matrix(
        portfolio=portfolio,
        structured=structured,
        outlook=outlook,
        forecast=data,
        settings=settings,
    )
    data["operation_matrix"] = matrix
    data["operation_plans"] = build_tied_operation_plans(
        structured,
        portfolio=portfolio,
        outlook=outlook,
        master_rows=matrix.get("master_rows"),
    )

    week_start = date.fromisoformat(str(data.get("week_start")))
    prior = load_forecast(_prior_trading_week_start(week_start))
    try:
        from agent_reach.daily_run.forecast_advanced import build_forecast_advanced_insights

        data["advanced_insights"] = build_forecast_advanced_insights(
            forecast=data,
            prior_forecast=prior,
            portfolio=portfolio,
            structured=structured,
            matrix=matrix,
            enriched_map=enriched_map,
            settings=settings,
        )
    except Exception:
        data["advanced_insights"] = {}

    if prior:
        verification = verify_prior_week_predictions(prior, settings=settings)
        verification["accuracy_trend"] = four_week_accuracy_trend(as_of=week_start, settings=settings)
        data["prior_week_verification"] = verification
        try:
            from agent_reach.daily_run.forecast_tracking import record_week_verification_to_tracking

            record_week_verification_to_tracking(verification, prior, settings=settings)
        except Exception:
            pass
        if persist_prior:
            prior["week_verification"] = verification
            try:
                from agent_reach.daily_run.week_forecast import save_forecast

                save_forecast(prior)
            except Exception:
                pass
    else:
        data["prior_week_verification"] = {
            "rows": [],
            "hits": 0,
            "total": 0,
            "accuracy_pct": None,
            "accuracy_trend": four_week_accuracy_trend(as_of=week_start, settings=settings),
        }

    risk_calendar = list((outlook or {}).get("risk_calendar") or [])
    data["risk_calendar"] = risk_calendar
    data["portfolio_snapshot"] = portfolio
    data["operation_matrix"] = matrix
    return data


def render_forecast_harness_evolution_markdown(
    harness_result: Optional[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> str:
    if not harness_result or harness_result.get("skipped"):
        return ""
    from agent_reach.daily_run.report_narrative import (
        _collect_harness_overlay_evolution_lines,
        _compact_harness_execution_summary,
    )

    skills = harness_result.get("forecast_skills") or {}
    overlay = skills.get("effective_overlay")
    overlay_lines = _collect_harness_overlay_evolution_lines(
        settings,
        effective_overlay=overlay,
        max_lines=16,
    )
    key_markers = (
        "宏观否决",
        "进攻阈值",
        "deploy_ratio",
        "max_position",
        "最低现金",
        "vol_scale",
        "bias",
        "calibration",
    )
    key_lines: list[str] = []
    secondary_lines: list[str] = []
    for line in overlay_lines:
        if any(marker in line for marker in key_markers):
            key_lines.append(line)
        else:
            secondary_lines.append(line)

    reason_lines: list[str] = []
    for block_key in ("forecast_calibrate", "layer_a", "layer_b"):
        block = harness_result.get(block_key) or skills.get(block_key) or {}
        if not isinstance(block, dict):
            continue
        summary = str(block.get("proposal_summary") or block.get("reason") or "").strip()
        if summary and summary not in reason_lines:
            reason_lines.append(summary[:120])
        for note in block.get("optimization_notes") or []:
            text = str(note).strip()
            if text and text not in reason_lines:
                reason_lines.append(text[:120])
            if len(reason_lines) >= 3:
                break
        changes = block.get("changes")
        if isinstance(changes, list):
            for note in changes:
                text = str(note).strip()
                if text and text not in reason_lines:
                    reason_lines.append(text[:120])
                if len(reason_lines) >= 3:
                    break

    lines = ["**Harness 进化（预测校准）**", ""]
    if key_lines:
        lines.append("**关键参数变化：**")
        lines.extend(f"- {item}" for item in key_lines[:6])
    if secondary_lines:
        lines.append("")
        lines.append("**次要参数变化：**")
        lines.extend(f"- {item}" for item in secondary_lines[:6])
    if reason_lines:
        lines.append("")
        lines.append("**调整原因：**")
        lines.extend(f"- {item}" for item in reason_lines[:3])
    execution = _compact_harness_execution_summary(harness_result)
    if execution:
        lines.append("")
        lines.append("**本次执行：**")
        lines.extend(f"- {item}" for item in execution[:3])
    if len(lines) <= 2:
        return ""
    return "\n".join(lines).strip()


def render_prior_week_verify_markdown(
    verification: dict[str, Any],
    *,
    advanced: Optional[dict[str, Any]] = None,
    harness_result: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> str:
    rows = verification.get("rows") or []
    if not rows:
        base = (
            "## 📋 上周预测验证\n\n"
            "- 暂无可验证的上周结构化预测（首次运行或缺少历史 forecast 文件）"
        )
    else:
        lines = ["## 📋 上周预测验证", ""]
        ws, we = verification.get("week_start"), verification.get("week_end")
        if ws and we:
            lines.append(f"**验证周期：** {ws} ~ {we}")
            lines.append("")
        lines.extend(
            [
                "| 上周预测 | 实际结果 | 验证 | 偏差 |",
                "|----------|----------|------|------|",
            ]
        )
        for row in rows:
            lines.append(
                f"| {row.get('prediction')} | {row.get('actual')} | {row.get('verify')} | {row.get('deviation')} |"
            )
        hits = verification.get("hits")
        total = verification.get("total")
        acc = verification.get("accuracy_pct")
        avg_dev = verification.get("avg_deviation_pct")
        if total:
            acc_s = f"{float(acc):.0f}%" if acc is not None else "—"
            dev_s = f"{float(avg_dev):.1f}%" if avg_dev is not None else "—"
            lines.append("")
            lines.append(f"→ **上周预测准确率：{hits}/{total} = {acc_s}**，平均偏差 {dev_s}")
        trend = verification.get("accuracy_trend") or []
        if trend:
            parts = [f"{float(t['accuracy_pct']):.0f}%" for t in trend if t.get("accuracy_pct") is not None]
            if parts:
                lines.append(f"→ **近{len(parts)}周准确率：** {' → '.join(parts)}")
        reasons = [r for r in verification.get("miss_reasons") or [] if r]
        if reasons:
            lines.append("")
            lines.append("**偏差原因（摘要）：** " + "；".join(reasons[:2]))
        base = "\n".join(lines).strip()

    adv = advanced or {}
    extras: list[str] = []
    try:
        from agent_reach.daily_run.forecast_advanced import (
            render_prior_operation_execution_markdown,
            render_scatter_history_markdown,
        )

        scatter_md = render_scatter_history_markdown(adv.get("scatter") or {})
        if scatter_md:
            extras.append(scatter_md)
        op_md = render_prior_operation_execution_markdown(adv.get("prior_operation_execution") or {})
        if op_md:
            extras.append(op_md)
    except Exception:
        pass
    if extras:
        base = base + "\n\n" + "\n\n".join(extras)
    harness_md = render_forecast_harness_evolution_markdown(
        harness_result,
        settings=settings,
    )
    if harness_md:
        base = base + "\n\n" + harness_md
    return base


def render_market_sector_markdown(structured: dict[str, Any]) -> str:
    scope = structured.get("content_scope") or {}
    lines = ["## 🌐 下周大盘与板块预测", ""]
    recap = scope.get("weekly_recap")
    if recap:
        lines.append(f"**本周回顾（1句）：** {recap}")
        lines.append("")
    macro = scope.get("macro_brief") or {}
    if macro.get("text"):
        lines.append(f"**宏观（核心）：** {macro['text']}")
        lines.append("")
    market = structured.get("market") or {}
    if market.get("text"):
        # Numeric band only — drop duplicated long evidence in this card
        lo = market.get("change_pct_low")
        hi = market.get("change_pct_high")
        conf = market.get("confidence_pct")
        index_name = market.get("index_name") or "沪深300"
        if lo is not None and hi is not None:
            conf_s = f"，置信度 {float(conf):.0f}%" if conf is not None else ""
            lines.append(
                f"- **{index_name}** {_fmt_pct(float(lo))}~{_fmt_pct(float(hi))}{conf_s}"
            )
    sectors = scope.get("sectors_scoped") or structured.get("sectors") or []
    if sectors:
        lines.append("")
        lines.append("**持仓所在板块：**")
        for sec in sectors:
            lines.append(f"- {sec.get('text')}")
    ref = scope.get("market_reference")
    if ref:
        lines.append("")
        lines.append(f"_{ref}_")
    extra = scope.get("extra_reading") or []
    if extra:
        lines.append("")
        lines.append(f"**延伸阅读：** {' · '.join(extra)}（完整分析见周六周报/调研摘要）")
    if len(lines) <= 2:
        lines.append("- 暂无大盘/板块结构化预测")
    return "\n".join(lines).strip()


def _plan_by_code(operation_plans: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        _normalize_code(str(p.get("code") or "")): p
        for p in operation_plans
        if p.get("code")
    }


def render_holdings_plans_markdown(
    structured: dict[str, Any],
    operation_plans: list[dict[str, Any]],
    *,
    advanced: Optional[dict[str, Any]] = None,
) -> str:
    scope = structured.get("content_scope") or {}
    lines = ["## 📊 持仓与观察池下周预测与操作预案", ""]
    lines.append("_持仓操作见「操作总表」；观察池列预测与因子，新建仓触发同表或 outlook。_")
    lines.append("")
    compact = scope.get("symbols_compact") or []
    watchlist_compact = scope.get("watchlist_compact") or []
    symbols = structured.get("symbols") or []

    if compact:
        lines.append("**持仓：**")
        for text in compact:
            lines.append(f"- {text}")
    elif operation_plans:
        for row in operation_plans:
            if row.get("role") == "watchlist":
                continue
            lines.append(f"- **{row.get('name')}** {row.get('prediction_text')}")
    else:
        lines.append("- 暂无持仓预测")

    if watchlist_compact:
        lines.extend(["", "**观察池：**"])
        for text in watchlist_compact:
            lines.append(f"- {text}")
    elif operation_plans:
        wl_plans = [r for r in operation_plans if r.get("role") == "watchlist"]
        if wl_plans:
            lines.extend(["", "**观察池：**"])
            for row in wl_plans:
                lines.append(f"- **{row.get('name')}** {row.get('prediction_text')}")

    buy_rows = scope.get("buy_candidates") or []
    if buy_rows:
        lines.extend(["", "**新建仓候选（非持仓）：**"])
        for row in buy_rows:
            lines.append(f"- {row.get('text')}")

    try:
        from agent_reach.daily_run.forecast_advanced import render_model_consistency_markdown

        model_md = render_model_consistency_markdown((advanced or {}).get("model_consistency") or [])
        if model_md:
            lines.extend(["", model_md])
    except Exception:
        pass

    cross = structured.get("cross_check") or {}
    if cross.get("issues"):
        lines.extend(["", "**数据核对：** " + "；".join(cross["issues"][:2])])
    return "\n".join(lines).strip()


def render_risk_response_markdown(
    risk_calendar: list[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> str:
    lines = ["## ⚠️ 下周风险事件与应对", ""]
    if not risk_calendar:
        lines.append("- 暂无已登记风险事件；默认应对：MSS<45 降仓至 50%，单票止损 -8%")
        return "\n".join(lines).strip()
    lines.extend(
        [
            "| 日期 | 事件 | 影响范围 | 应对预案 |",
            "|------|------|----------|----------|",
        ]
    )
    for row in risk_calendar[:8]:
        ds = str(row.get("date") or "")[5:]
        severity = str(row.get("severity") or "中")
        scope = str(row.get("scope") or "—")
        event = str(row.get("event") or "—")
        if severity in ("高", "HIGH", "high"):
            response = "事件前降仓 10-15%；波动放大时暂停新建仓"
        elif scope == "大盘波动":
            response = "提高现金至 50%+；指数跌破5日线减至 40%"
        else:
            response = "相关持仓减半；止损收紧至 -5%"
        lines.append(f"| {ds} | {event} | {scope} | {response} |")
    return "\n".join(lines).strip()


def render_confidence_limitations_markdown(
    forecast: dict[str, Any],
    structured: dict[str, Any],
) -> str:
    cal = forecast.get("calibration_used") or {}
    hit_rate = cal.get("hit_rate")
    sym_count = len(structured.get("symbols") or [])
    sector_count = len(structured.get("sectors") or [])
    lines = ["## 🎯 预测置信度与局限性说明", ""]
    market = structured.get("market") or {}
    mconf = market.get("confidence_pct")
    if mconf is not None:
        lines.append(
            f"- **大盘置信度：** {confidence_tier_detail(float(mconf))} · "
            f"操作建议：{position_hint_for_confidence(float(mconf))}"
        )
    low_conf = [
        s for s in structured.get("symbols") or []
        if _optional_float(s.get("confidence_pct")) is not None and float(s["confidence_pct"]) < 60
    ]
    if low_conf:
        names = "、".join(str(s.get("name")) for s in low_conf[:4])
        lines.append(f"- **低置信度标的：** {names}（建议轻仓或观望）")
    if hit_rate is not None:
        lines.append(f"- **历史校准命中率：** {float(hit_rate):.0%}（滚动更新）")
    scope = structured.get("content_scope") or {}
    lines.append(f"- **下周聚焦：** 持仓 {sym_count} 只 · 相关板块 {sector_count} 个（已剔除无关热点）")
    extra = scope.get("extra_reading") or []
    if extra:
        lines.append(f"- **延伸阅读：** {' · '.join(extra)}")
    lines.append(f"- **本周详情：** {scope.get('weekly_report_link') or '详见本周周报'}")
    lines.append(
        "- **局限性：** 预测基于 MSS/Kronos/历史波动外推，不含未披露信息与黑天鹅；"
        "区间外结果按操作预案执行"
    )
    prob_note = structured.get("probability_note")
    if prob_note:
        lines.append(f"- **概率分布：** {prob_note}")
    return "\n".join(lines).strip()


def render_structured_forecast_sections(
    forecast: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> list[tuple[str, str]]:
    """Return structured (label, markdown) sections for Sunday forecast push."""
    structured = forecast.get("structured_predictions") or {}
    verification = forecast.get("prior_week_verification") or {}
    operation_plans = forecast.get("operation_plans") or []
    matrix = forecast.get("operation_matrix") or {}

    sections: list[tuple[str, str]] = []
    advanced = forecast.get("advanced_insights") or {}
    harness_result = forecast.get("harness_result") or {}
    portfolio = forecast.get("portfolio_snapshot") or forecast.get("_portfolio")
    verify_md = render_prior_week_verify_markdown(
        verification,
        advanced=advanced,
        harness_result=harness_result,
        settings=settings,
    )
    if verify_md.strip():
        sections.append((_FORECAST_SECTION_LABELS[0], verify_md))

    if not matrix and structured:
        matrix = build_forecast_operation_matrix(
            portfolio=portfolio,
            structured=structured,
            outlook=forecast.get("outlook"),
            forecast=forecast,
            settings=settings,
        )

    if not advanced and structured:
        try:
            from agent_reach.daily_run.forecast_advanced import build_forecast_advanced_insights

            advanced = build_forecast_advanced_insights(
                forecast=forecast,
                prior_forecast=None,
                portfolio=forecast.get("_portfolio"),
                structured=structured,
                matrix=matrix,
                settings=settings,
            )
        except Exception:
            advanced = {}

    master_md = render_master_operation_markdown(matrix) if matrix else ""
    if master_md.strip():
        sections.append((_FORECAST_SECTION_LABELS[1], master_md))

    scenario_md = render_scenario_markdown(matrix) if matrix else ""
    if scenario_md.strip():
        try:
            from agent_reach.daily_run.forecast_advanced import render_stress_tests_markdown

            stress_md = render_stress_tests_markdown(advanced.get("stress_tests") or [])
            if stress_md:
                scenario_md = scenario_md + "\n\n" + stress_md
        except Exception:
            pass
        sections.append((_FORECAST_SECTION_LABELS[2], scenario_md))

    market_md = render_market_sector_markdown(structured)
    if market_md.strip():
        sections.append((_FORECAST_SECTION_LABELS[3], market_md))

    holdings_md = render_holdings_plans_markdown(structured, operation_plans, advanced=advanced)
    if holdings_md.strip():
        sections.append((_FORECAST_SECTION_LABELS[4], holdings_md))

    homogeneity = structured.get("homogeneity_warning") or forecast.get("homogeneity_warning")
    if isinstance(homogeneity, dict) and homogeneity.get("message"):
        hom_md = (
            f"⚠️ **{homogeneity['message']}**\n\n"
            f"- 建议：{homogeneity.get('suggestion') or '复核模型分歧与遗漏因素'}"
        )
        sections.append(("模型同质化", hom_md))

    timeline_md = render_timeline_markdown(matrix) if matrix else ""
    if timeline_md.strip():
        sections.append((_FORECAST_SECTION_LABELS[5], timeline_md))

    from agent_reach.daily_run.deepseek_interpretation_cards import render_deepseek_interpretation_markdown

    interpret_md = render_deepseek_interpretation_markdown(
        forecast.get("llm_narrative"),
        job="forecast",
        settings=settings,
    )
    if interpret_md.strip():
        label = (
            "DeepSeek解读"
            if str((forecast.get("llm_narrative") or {}).get("planner") or "") == "llm"
            else "规则解读"
        )
        sections.append((label, interpret_md))

    return sections

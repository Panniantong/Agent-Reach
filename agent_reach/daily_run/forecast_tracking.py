# -*- coding: utf-8
"""Weekly forecast accuracy tracking — daily checks, weekend metrics, monthly optimization."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Optional

from agent_reach.daily_run.snapshot_builder import _normalize_code
from agent_reach.daily_run.trade_calendar import today_shanghai
from agent_reach.daily_run.week_forecast import forecasts_dir, load_forecast

TARGET_INTERVAL_HIT_PCT = 70.0
TARGET_DIRECTION_ACCURACY_PCT = 60.0
TARGET_AVG_DEVIATION_PCT = 3.0


def tracking_path():
    return forecasts_dir() / "tracking.json"


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_pct(value: float, *, signed: bool = True) -> str:
    if signed:
        return f"{value:+.1f}%"
    return f"{value:.1f}%"


def _target_status(actual: Optional[float], target: float, *, lower_is_better: bool = False) -> str:
    if actual is None:
        return "—"
    ok = actual >= target if not lower_is_better else actual <= target
    return "✅ 达标" if ok else "⚠️ 未达标"


def _symbol_price_on_day(
    pred: dict[str, Any],
    forecast: dict[str, Any],
    ds: str,
) -> Optional[float]:
    base = _optional_float(pred.get("base_price"))
    if base is None or base <= 0:
        return None
    cum = 0.0
    for day in sorted(forecast.get("trading_days") or []):
        if day > ds:
            break
        sym_actual = ((forecast.get("actuals") or {}).get(day) or {}).get("symbols", {})
        row = sym_actual.get(str(pred.get("code") or "")) or sym_actual.get(_normalize_code(str(pred.get("code") or "")))
        if not row:
            continue
        chg = _optional_float(row.get("change_pct"))
        if chg is not None:
            cum += chg
    if cum == 0.0 and ds not in (forecast.get("actuals") or {}):
        return base
    return round(base * (1 + cum / 100), 2)


def count_days_in_price_band(
    pred: dict[str, Any],
    forecast: dict[str, Any],
    *,
    as_of: date,
) -> tuple[int, int]:
    lo = _optional_float(pred.get("price_low"))
    hi = _optional_float(pred.get("price_high"))
    if lo is None or hi is None:
        return 0, 0
    elapsed = [d for d in (forecast.get("trading_days") or []) if d <= as_of.isoformat()]
    if not elapsed:
        return 0, 0
    in_band = 0
    for ds in elapsed:
        px = _symbol_price_on_day(pred, forecast, ds)
        if px is not None and lo <= px <= hi:
            in_band += 1
    return in_band, len(elapsed)


def _market_cum_return(forecast: dict[str, Any], *, as_of: date) -> Optional[float]:
    cum = 0.0
    found = False
    for ds in sorted(forecast.get("trading_days") or []):
        if ds > as_of.isoformat():
            break
        day_actual = (forecast.get("actuals") or {}).get(ds) or {}
        for sym_actual in (day_actual.get("symbols") or {}).values():
            chg = _optional_float(sym_actual.get("change_pct"))
            if chg is not None:
                cum += chg
                found = True
                break
    if not found:
        return None
    return round(cum / max(1, len([d for d in (forecast.get("trading_days") or []) if d <= as_of.isoformat()])), 2)


def build_daily_structured_checks(
    forecast: Optional[dict[str, Any]],
    snapshot: Optional[dict[str, Any]],
    *,
    trading_date: Optional[date] = None,
) -> list[dict[str, Any]]:
    """Daily close: verify structured week bands still hold."""
    if not forecast or not snapshot:
        return []
    structured = forecast.get("structured_predictions") or {}
    if not structured:
        return []

    d = trading_date or today_shanghai()
    ds = d.isoformat()
    if ds not in (forecast.get("trading_days") or []):
        return []

    from agent_reach.daily_run.symbols import build_enriched_symbols

    enriched = build_enriched_symbols(snapshot)
    checks: list[dict[str, Any]] = []

    market = structured.get("market") or {}
    m_lo = _optional_float(market.get("change_pct_low"))
    m_hi = _optional_float(market.get("change_pct_high"))
    if m_lo is not None and m_hi is not None:
        m_cum = _market_cum_return(forecast, as_of=d)
        elapsed = len([x for x in (forecast.get("trading_days") or []) if x <= ds])
        if m_cum is not None:
            in_band = m_lo <= m_cum <= m_hi
            status = "在区间内" if in_band else "偏离区间"
            index_name = market.get("index_name") or "沪深300"
            checks.append(
                {
                    "kind": "market",
                    "name": index_name,
                    "text": (
                        f"周预测验证：{index_name}预测{_fmt_pct(m_lo)}~{_fmt_pct(m_hi)}，"
                        f"本周累计{_fmt_pct(m_cum)}，{status}（{elapsed}/{len(forecast.get('trading_days') or [])}日）"
                    ),
                    "in_band": in_band,
                }
            )

    for pred in structured.get("symbols") or []:
        code = _normalize_code(str(pred.get("code") or ""))
        lo = _optional_float(pred.get("price_low"))
        hi = _optional_float(pred.get("price_high"))
        if not code or lo is None or hi is None:
            continue
        row = enriched.get(code) or {}
        current = _optional_float(row.get("price"))
        if current is None:
            continue
        in_band = lo <= current <= hi
        if in_band:
            status = "在区间内"
        elif current < lo:
            status = "低于区间下沿"
        else:
            status = "高于区间上沿"
        in_days, elapsed = count_days_in_price_band(pred, forecast, as_of=d)
        name = str(pred.get("name") or code)
        checks.append(
            {
                "kind": "symbol",
                "code": code,
                "name": name,
                "text": (
                    f"周预测验证：{name}预测区间{lo:.0f}-{hi:.0f}元，"
                    f"当前{current:.0f}元，{status}（{in_days}/{elapsed}日）"
                ),
                "in_band": in_band,
                "days_in_band": in_days,
                "days_elapsed": elapsed,
            }
        )
    return checks


def _kronos_day_direction(change_pct: Optional[float]) -> str:
    if change_pct is None:
        return "flat"
    val = float(change_pct)
    if val > 0.3:
        return "up"
    if val < -0.3:
        return "down"
    return "flat"


def _actual_direction(change_pct: Optional[float]) -> str:
    return _kronos_day_direction(change_pct)


def build_kronos_divergence_day_checks(
    forecast: Optional[dict[str, Any]],
    snapshot: Optional[dict[str, Any]],
    *,
    trading_date: Optional[date] = None,
) -> list[dict[str, Any]]:
    """Daily close: validate Kronos direction on marked divergence days only."""
    if not forecast or not snapshot:
        return []
    d = trading_date or today_shanghai()
    ds = d.isoformat()
    if ds not in (forecast.get("trading_days") or []):
        return []

    from agent_reach.daily_run.symbols import build_enriched_symbols

    enriched = build_enriched_symbols(snapshot)
    checks: list[dict[str, Any]] = []
    for code, sym in (forecast.get("symbols") or {}).items():
        if ds not in (sym.get("kronos_divergence_days") or []):
            continue
        row = enriched.get(_normalize_code(str(code))) or {}
        actual = _optional_float(row.get("change_pct"))
        if actual is None:
            continue
        day_pred = (sym.get("days") or {}).get(ds) or {}
        kronos_chg = _optional_float(day_pred.get("kronos_change_pct"))
        if kronos_chg is None:
            k_day = ((sym.get("kronos") or {}).get("days") or {}).get(ds) or {}
            kronos_chg = _optional_float(k_day.get("change_pct"))
        if kronos_chg is None:
            continue
        pred_dir = _kronos_day_direction(kronos_chg)
        actual_dir = _actual_direction(actual)
        hit = pred_dir == actual_dir
        name = str(sym.get("name") or code)
        dir_cn = {"up": "↑", "down": "↓", "flat": "→"}
        checks.append(
            {
                "kind": "kronos_divergence",
                "code": _normalize_code(str(code)),
                "name": name,
                "text": (
                    f"Kronos 分歧日：{name} 日预测 {dir_cn.get(pred_dir, pred_dir)}"
                    f"（{kronos_chg:+.2f}%）/ 实际 {dir_cn.get(actual_dir, actual_dir)}"
                    f"（{actual:+.2f}%）"
                ),
                "hit": hit,
                "predicted_direction": pred_dir,
                "actual_direction": actual_dir,
            }
        )
    return checks


def render_kronos_divergence_day_markdown(checks: list[dict[str, Any]]) -> str:
    div_checks = [c for c in checks if c.get("kind") == "kronos_divergence"]
    if not div_checks:
        return ""
    lines = ["**Kronos 分歧日验证（当日）：**"]
    for item in div_checks[:6]:
        mark = "✅" if item.get("hit") else "❌"
        lines.append(f"- {mark} {item.get('text')}")
    return "\n".join(lines).strip()


def render_daily_structured_checks_markdown(checks: list[dict[str, Any]]) -> str:
    if not checks:
        return ""
    lines = ["**周预测关键判断（结构化）：**"]
    for item in checks[:6]:
        if item.get("kind") == "kronos_divergence":
            continue
        mark = "✅" if item.get("in_band") else "⚠️"
        lines.append(f"- {mark} {item.get('text')}")
    div_md = render_kronos_divergence_day_markdown(checks)
    if div_md:
        lines.extend(["", div_md])
    return "\n".join(lines).strip()


def _direction_hit(pred: dict[str, Any], actual: Optional[float]) -> Optional[bool]:
    if actual is None:
        return None
    mid = _optional_float(pred.get("change_pct_mid"))
    if mid is None:
        lo = _optional_float(pred.get("change_pct_low"))
        hi = _optional_float(pred.get("change_pct_high"))
        mid = (lo + hi) / 2 if lo is not None and hi is not None else None
    if mid is None:
        return None
    if abs(mid) <= 0.3:
        return abs(actual) <= 1.0
    return (mid > 0 and actual > 0.3) or (mid < 0 and actual < -0.3)


def _parse_target_weight_pct(target: str) -> Optional[float]:
    text = str(target or "")
    if "→" in text:
        text = text.split("→")[-1]
    text = text.replace("维持", "").replace("%", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def compute_operation_return_vs_hold(
    forecast: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Compare hold-at-start weights vs operation-matrix target weights."""
    structured = forecast.get("structured_predictions") or {}
    matrix = forecast.get("operation_matrix") or {}
    rows = matrix.get("master_rows") or []
    if not rows:
        return {}

    sym_chg: dict[str, float] = {}
    for pred in structured.get("symbols") or []:
        code = _normalize_code(str(pred.get("code") or ""))
        chg = _optional_float(pred.get("change_pct_mid"))
        if chg is None:
            from agent_reach.daily_run.forecast_structured import _symbol_week_actuals

            _, _, chg = _symbol_week_actuals(pred, forecast)
        if code and chg is not None:
            sym_chg[code] = float(chg)

    hold_ret = 0.0
    plan_ret = 0.0
    hold_w = 0.0
    plan_w = 0.0
    for row in rows:
        code = str(row.get("code") or "")
        if code == "CASH":
            continue
        chg = sym_chg.get(_normalize_code(code))
        if chg is None:
            continue
        cur_w = float(row.get("current_weight_pct") or 0) / 100.0
        tgt = _parse_target_weight_pct(str(row.get("target_weight") or ""))
        tgt_w = (tgt / 100.0) if tgt is not None else cur_w
        hold_ret += cur_w * chg
        plan_ret += tgt_w * chg
        hold_w += cur_w
        plan_w += tgt_w

    if hold_w <= 0:
        return {}
    hold_pct = round(hold_ret / hold_w, 2) if hold_w else None
    plan_pct = round(plan_ret / plan_w, 2) if plan_w else None
    alpha = round(plan_pct - hold_pct, 2) if hold_pct is not None and plan_pct is not None else None
    return {
        "hold_return_pct": hold_pct,
        "plan_return_pct": plan_pct,
        "alpha_pct": alpha,
        "note": "按操作总表目标仓位加权本周涨跌幅（近似，不含交易成本）",
    }


def enrich_week_verification_metrics(
    verification: dict[str, Any],
    forecast: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Add interval/direction/operation metrics to week verification payload."""
    out = dict(verification)
    rows = list(out.get("rows") or [])
    scored = [r for r in rows if r.get("hit") is not None]
    interval_hits = sum(1 for r in scored if r.get("hit"))
    interval_total = len(scored)
    interval_hit_rate = round(interval_hits / interval_total * 100.0, 1) if interval_total else None

    structured = forecast.get("structured_predictions") or {}
    from agent_reach.daily_run.weekly_card_metrics import fetch_benchmark_weekly_return

    ws = date.fromisoformat(str(forecast.get("week_start")))
    we = date.fromisoformat(str(forecast.get("week_end")))
    bench = fetch_benchmark_weekly_return(ws, we, settings=settings)
    bench_pct = _optional_float(bench.get("return_pct"))

    dir_scored: list[bool] = []
    market = structured.get("market") or {}
    if bench_pct is not None:
        hit = _direction_hit(market, bench_pct)
        if hit is not None:
            dir_scored.append(hit)
    for pred in structured.get("symbols") or []:
        from agent_reach.daily_run.forecast_structured import _symbol_week_actuals

        _, _, chg = _symbol_week_actuals(pred, forecast)
        hit = _direction_hit(pred, chg)
        if hit is not None:
            dir_scored.append(hit)

    direction_accuracy = (
        round(sum(1 for h in dir_scored if h) / len(dir_scored) * 100.0, 1) if dir_scored else None
    )
    operation_returns = compute_operation_return_vs_hold(forecast, settings=settings)

    out["metrics"] = {
        "interval_hit_rate_pct": interval_hit_rate,
        "interval_hits": interval_hits,
        "interval_total": interval_total,
        "direction_accuracy_pct": direction_accuracy,
        "direction_hits": sum(1 for h in dir_scored if h),
        "direction_total": len(dir_scored),
        "avg_deviation_pct": out.get("avg_deviation_pct"),
        "operation_returns": operation_returns,
        "targets": {
            "interval_hit_rate_pct": TARGET_INTERVAL_HIT_PCT,
            "direction_accuracy_pct": TARGET_DIRECTION_ACCURACY_PCT,
            "avg_deviation_pct": TARGET_AVG_DEVIATION_PCT,
        },
    }
    return out


def build_structured_week_review(
    forecast: Optional[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not forecast:
        return {}
    stored = forecast.get("week_verification")
    if isinstance(stored, dict) and stored.get("metrics"):
        return stored
    from agent_reach.daily_run.forecast_structured import verify_prior_week_predictions

    base = verify_prior_week_predictions(forecast, settings=settings)
    if not base.get("rows"):
        return base
    return enrich_week_verification_metrics(base, forecast, settings=settings)


def load_tracking_store() -> dict[str, Any]:
    path = tracking_path()
    if not path.exists():
        return {"error_cases": [], "monthly": {}, "type_totals": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("error_cases", [])
            data.setdefault("monthly", {})
            data.setdefault("type_totals", {})
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"error_cases": [], "monthly": {}, "type_totals": {}}


def save_tracking_store(data: dict[str, Any]) -> None:
    path = tracking_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _record_type_bucket(store: dict[str, Any], month: str, kind: str, hit: bool) -> None:
    monthly = store.setdefault("monthly", {})
    bucket = monthly.setdefault(month, {})
    row = bucket.setdefault(kind, {"hits": 0, "total": 0})
    row["total"] = int(row.get("total") or 0) + 1
    if hit:
        row["hits"] = int(row.get("hits") or 0) + 1

    totals = store.setdefault("type_totals", {})
    trow = totals.setdefault(kind, {"hits": 0, "total": 0})
    trow["total"] = int(trow.get("total") or 0) + 1
    if hit:
        trow["hits"] = int(trow.get("hits") or 0) + 1


def record_week_verification_to_tracking(
    verification: dict[str, Any],
    forecast: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Persist weekly scores + error cases for monthly optimization."""
    if not verification.get("rows"):
        return load_tracking_store()

    store = load_tracking_store()
    ws = str(forecast.get("week_start") or verification.get("week_start") or "")[:10]
    try:
        month = _month_key(date.fromisoformat(ws))
    except ValueError:
        month = _month_key(today_shanghai())

    structured = forecast.get("structured_predictions") or {}
    if structured.get("market"):
        market_rows = [r for r in verification.get("rows") or [] if "大盘" in str(r.get("prediction") or "")]
        if market_rows and market_rows[0].get("hit") is not None:
            _record_type_bucket(store, month, "market", bool(market_rows[0]["hit"]))

    sym_names = {str(s.get("name") or s.get("code")) for s in structured.get("symbols") or []}
    for row in verification.get("rows") or []:
        pred_s = str(row.get("prediction") or "")
        if row.get("hit") is None:
            continue
        if any(name in pred_s for name in sym_names if name):
            _record_type_bucket(store, month, "symbol", bool(row["hit"]))
            if not row.get("hit"):
                store["error_cases"].append(
                    {
                        "week_start": ws,
                        "type": "symbol",
                        "prediction": pred_s,
                        "actual": row.get("actual"),
                        "reason": row.get("reason") or "",
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
        elif "超额" in pred_s:
            _record_type_bucket(store, month, "sector", bool(row["hit"]))
            if not row.get("hit"):
                store["error_cases"].append(
                    {
                        "week_start": ws,
                        "type": "sector",
                        "prediction": pred_s,
                        "actual": row.get("actual"),
                        "reason": row.get("reason") or "",
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

    metrics = verification.get("metrics") or {}
    dir_total = int(metrics.get("direction_total") or 0)
    dir_hits = int(metrics.get("direction_hits") or 0)
    if dir_total:
        bucket = store.setdefault("monthly", {}).setdefault(month, {})
        bucket["direction"] = {"hits": dir_hits, "total": dir_total}

    store["error_cases"] = (store.get("error_cases") or [])[-80:]
    save_tracking_store(store)
    return store


def build_monthly_accuracy_summary(
    *,
    as_of: Optional[date] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    store = load_tracking_store()
    d = as_of or today_shanghai()
    month = _month_key(d)
    month_data = (store.get("monthly") or {}).get(month) or {}
    rows: list[dict[str, Any]] = []
    for kind in ("market", "symbol", "sector", "direction"):
        bucket = month_data.get(kind) or {}
        total = int(bucket.get("total") or 0)
        if total <= 0:
            continue
        hits = int(bucket.get("hits") or 0)
        acc = round(hits / total * 100.0, 1)
        rows.append({"type": kind, "hits": hits, "total": total, "accuracy_pct": acc})

    low_types = [r for r in rows if float(r["accuracy_pct"]) < 50.0]
    totals = store.get("type_totals") or {}
    long_low = [
        k
        for k, v in totals.items()
        if int(v.get("total") or 0) >= 4
        and int(v.get("hits") or 0) / int(v.get("total") or 1) * 100.0 < 50.0
    ]
    recent_errors = list(reversed(store.get("error_cases") or []))[:5]
    return {
        "month": month,
        "rows": rows,
        "low_accuracy_types": low_types,
        "chronic_low_types": long_low,
        "recent_error_cases": recent_errors,
    }


def render_structured_week_verify_markdown(review: dict[str, Any]) -> list[str]:
    if not review or not review.get("rows"):
        return []
    metrics = review.get("metrics") or {}
    lines = ["## 📊 本周周预测复盘（结构化）", ""]
    interval = metrics.get("interval_hit_rate_pct")
    direction = metrics.get("direction_accuracy_pct")
    avg_dev = metrics.get("avg_deviation_pct")
    targets = metrics.get("targets") or {}
    lines.extend(
        [
            "| 指标 | 实际 | 目标 | 状态 |",
            "|------|------|------|------|",
            f"| 区间命中率 | {interval:.1f}% | >{targets.get('interval_hit_rate_pct', TARGET_INTERVAL_HIT_PCT):.0f}% | "
            f"{_target_status(interval, float(targets.get('interval_hit_rate_pct') or TARGET_INTERVAL_HIT_PCT))} |"
            if interval is not None
            else f"| 区间命中率 | — | >{TARGET_INTERVAL_HIT_PCT:.0f}% | — |",
            f"| 方向准确率 | {direction:.1f}% | >{targets.get('direction_accuracy_pct', TARGET_DIRECTION_ACCURACY_PCT):.0f}% | "
            f"{_target_status(direction, float(targets.get('direction_accuracy_pct') or TARGET_DIRECTION_ACCURACY_PCT))} |"
            if direction is not None
            else f"| 方向准确率 | — | >{TARGET_DIRECTION_ACCURACY_PCT:.0f}% | — |",
            f"| 平均偏差 | {avg_dev:.1f}% | <{targets.get('avg_deviation_pct', TARGET_AVG_DEVIATION_PCT):.0f}% | "
            f"{_target_status(avg_dev, float(targets.get('avg_deviation_pct') or TARGET_AVG_DEVIATION_PCT), lower_is_better=True)} |"
            if avg_dev is not None
            else f"| 平均偏差 | — | <{TARGET_AVG_DEVIATION_PCT:.0f}% | — |",
        ]
    )
    op = metrics.get("operation_returns") or {}
    if op.get("hold_return_pct") is not None and op.get("plan_return_pct") is not None:
        alpha = op.get("alpha_pct")
        alpha_s = _fmt_pct(float(alpha)) if alpha is not None else "—"
        lines.append(
            f"| 操作建议收益 | 计划 {_fmt_pct(float(op['plan_return_pct']))} vs "
            f"持有 {_fmt_pct(float(op['hold_return_pct']))}（α {alpha_s}） | — | — |"
        )
    lines.append("")
    ws, we = review.get("week_start"), review.get("week_end")
    if ws and we:
        lines.append(f"**验证周期：** {ws} ~ {we}")
        lines.append("")
    lines.extend(
        [
            "| 预测项 | 实际 | 验证 | 偏差 |",
            "|----------|------|------|------|",
        ]
    )
    for row in review.get("rows") or []:
        lines.append(
            f"| {row.get('prediction')} | {row.get('actual')} | {row.get('verify')} | {row.get('deviation')} |"
        )
    hits = review.get("hits")
    total = review.get("total")
    acc = review.get("accuracy_pct")
    if total:
        acc_s = f"{float(acc):.0f}%" if acc is not None else "—"
        lines.append("")
        lines.append(f"→ **结构化准确率：{hits}/{total} = {acc_s}**")
    return lines


def render_monthly_optimization_markdown(summary: dict[str, Any]) -> list[str]:
    if not summary:
        return []
    rows = summary.get("rows") or []
    if not rows and not summary.get("recent_error_cases"):
        return []
    lines = ["## 🔧 预测持续优化（本月）", ""]
    if rows:
        lines.extend(
            [
                "| 预测类型 | 命中 | 总数 | 准确率 |",
                "|----------|------|------|--------|",
            ]
        )
        type_cn = {"market": "大盘", "symbol": "个股", "sector": "板块", "direction": "方向"}
        for row in rows:
            kind = type_cn.get(str(row.get("type")), str(row.get("type")))
            acc = float(row.get("accuracy_pct") or 0)
            flag = " ⚠️" if acc < 50 else ""
            lines.append(
                f"| {kind} | {row.get('hits')} | {row.get('total')} | {acc:.1f}%{flag} |"
            )
        lines.append("")
    chronic = summary.get("chronic_low_types") or []
    if chronic:
        lines.append(
            f"- **长期偏低：** {', '.join(chronic)} 准确率 <50%，建议收紧区间或减少该类预测"
        )
    low = summary.get("low_accuracy_types") or []
    if low:
        names = "、".join(str(r.get("type")) for r in low)
        lines.append(f"- **本月偏弱：** {names}，需分析模型/数据源")
    errors = summary.get("recent_error_cases") or []
    if errors:
        lines.extend(["", "**近期错误案例（摘要）：**"])
        for case in errors[:3]:
            lines.append(
                f"- {case.get('week_start')} {case.get('type')} · {case.get('prediction')} → "
                f"实际 {case.get('actual')}（{case.get('reason') or '见复盘'}）"
            )
    lines.append("")
    return lines

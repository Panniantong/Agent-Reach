# -*- coding: utf-8
"""Daily close review vs week forecast — accuracy tracking and calibration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from agent_reach.daily_run.snapshot_builder import _normalize_code
from agent_reach.daily_run.symbols import build_enriched_symbols
from agent_reach.daily_run.trade_calendar import today_shanghai
from agent_reach.daily_run.week_forecast import (
    load_active_forecast,
    load_calibration,
    save_calibration,
    save_forecast,
)


@dataclass
class SymbolEval:
    code: str
    name: str
    role: str
    predicted_direction: str
    predicted_range: list[float]
    actual_change_pct: Optional[float]
    hit: bool
    error_pct: Optional[float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "role": self.role,
            "predicted_direction": self.predicted_direction,
            "predicted_range": self.predicted_range,
            "actual_change_pct": self.actual_change_pct,
            "hit": self.hit,
            "error_pct": self.error_pct,
        }


@dataclass
class ForecastDayReview:
    date: str
    symbol_evals: list[SymbolEval] = field(default_factory=list)
    symbol_hits: int = 0
    symbol_total: int = 0
    accuracy: float = 0.0
    mss_predicted: Optional[list[float]] = None
    mss_actual: Optional[float] = None
    mss_hit: Optional[bool] = None
    calibration_before: dict[str, Any] = field(default_factory=dict)
    calibration_after: dict[str, Any] = field(default_factory=dict)
    optimization_notes: list[str] = field(default_factory=list)
    kronos_review: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "symbol_evals": [s.to_dict() for s in self.symbol_evals],
            "symbol_hits": self.symbol_hits,
            "symbol_total": self.symbol_total,
            "accuracy": self.accuracy,
            "mss_predicted": self.mss_predicted,
            "mss_actual": self.mss_actual,
            "mss_hit": self.mss_hit,
            "calibration_before": self.calibration_before,
            "calibration_after": self.calibration_after,
            "optimization_notes": self.optimization_notes,
            "kronos_review": self.kronos_review,
        }


def _actual_direction(chg: float) -> str:
    if chg > 0.3:
        return "up"
    if chg < -0.3:
        return "down"
    return "flat"


def _symbol_hit(
    predicted: dict[str, Any],
    actual_chg: float,
    *,
    kronos_day: Optional[dict[str, Any]] = None,
) -> tuple[bool, float]:
    lo, hi = predicted.get("change_pct_range") or [0, 0]
    lo, hi = float(lo), float(hi)
    in_range = lo <= actual_chg <= hi
    pred_dir = predicted.get("direction") or "flat"
    act_dir = _actual_direction(actual_chg)
    dir_hit = pred_dir == act_dir or (pred_dir == "flat" and abs(actual_chg) <= 1.0)
    expected = float(predicted.get("expected_change_pct") or (lo + hi) / 2)
    error = actual_chg - expected
    kronos_hit = None
    if kronos_day and kronos_day.get("change_pct") is not None:
        k_chg = float(kronos_day["change_pct"])
        k_dir = kronos_day.get("direction") or _actual_direction(k_chg)
        kronos_hit = k_dir == act_dir or abs(actual_chg - k_chg) <= max(1.5, abs(k_chg) * 0.5)
    hit = in_range or dir_hit
    if kronos_hit is True and not hit:
        hit = True
        error = actual_chg - float(kronos_day.get("change_pct", expected))
    return hit, round(error, 2)


def evaluate_day_forecast(
    forecast: dict[str, Any],
    snapshot: dict[str, Any],
    trading_date: date,
    *,
    mss_actual: Optional[float] = None,
) -> ForecastDayReview:
    """Compare today's forecast vs snapshot actuals."""
    ds = trading_date.isoformat()
    enriched = build_enriched_symbols(snapshot)
    evals: list[SymbolEval] = []

    for code, sym in (forecast.get("symbols") or {}).items():
        day_pred = (sym.get("days") or {}).get(ds)
        if not day_pred:
            continue
        row = enriched.get(_normalize_code(code), {})
        actual = row.get("change_pct")
        actual_f = float(actual) if actual is not None else None
        hit = False
        error = None
        kronos_block = (forecast.get("kronos_paths") or {}).get(code) or sym.get("kronos") or {}
        k_day = (kronos_block.get("days") or {}).get(ds) if kronos_block.get("available") else None
        if actual_f is not None:
            hit, error = _symbol_hit(day_pred, actual_f, kronos_day=k_day)
        evals.append(
            SymbolEval(
                code=code,
                name=str(sym.get("name") or code),
                role=str(sym.get("role") or ""),
                predicted_direction=str(day_pred.get("direction") or "flat"),
                predicted_range=[float(x) for x in (day_pred.get("change_pct_range") or [0, 0])],
                actual_change_pct=actual_f,
                hit=hit,
                error_pct=error,
            )
        )

    hits = sum(1 for e in evals if e.hit)
    total = len(evals)
    accuracy = round(hits / total, 3) if total else 0.0

    mss_pred_row = (forecast.get("mss_daily") or {}).get(ds) or {}
    mss_range = mss_pred_row.get("range")
    mss_hit = None
    if mss_actual is not None and mss_range and len(mss_range) == 2:
        mss_hit = float(mss_range[0]) <= float(mss_actual) <= float(mss_range[1])

    return ForecastDayReview(
        date=ds,
        symbol_evals=evals,
        symbol_hits=hits,
        symbol_total=total,
        accuracy=accuracy,
        mss_predicted=mss_range,
        mss_actual=mss_actual,
        mss_hit=mss_hit,
        calibration_before=load_calibration(),
    )


def optimize_calibration(
    review: ForecastDayReview,
    calibration: dict[str, Any],
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Nudge bias/vol_scale from today's forecast errors to improve next predictions."""
    cfg = (settings or {}).get("week_forecast") or {}
    lr = float(cfg.get("calibration_learning_rate", 0.15))
    max_bias = float(cfg.get("max_bias_pct", 3.0))
    min_vol, max_vol = float(cfg.get("min_vol_scale", 0.6)), float(cfg.get("max_vol_scale", 1.6))

    cal = dict(calibration)
    errors = [e.error_pct for e in review.symbol_evals if e.error_pct is not None]
    notes: list[str] = []

    if errors:
        mean_err = sum(errors) / len(errors)
        old_bias = float(cal.get("bias_pct") or 0)
        new_bias = max(-max_bias, min(max_bias, old_bias + mean_err * lr))
        cal["bias_pct"] = round(new_bias, 3)
        if abs(new_bias - old_bias) > 0.01:
            notes.append(f"bias {old_bias:+.2f}% → {new_bias:+.2f}%（均值误差 {mean_err:+.2f}%）")

        misses = [e for e in review.symbol_evals if not e.hit and e.actual_change_pct is not None]
        if len(misses) >= 2:
            old_vol = float(cal.get("vol_scale") or 1.0)
            new_vol = max(min_vol, min(max_vol, old_vol * (1 + lr * 0.2)))
            cal["vol_scale"] = round(new_vol, 3)
            notes.append(f"vol_scale {old_vol:.2f} → {new_vol:.2f}（扩大预测区间）")

    reviews = int(cal.get("reviews") or 0) + 1
    cal["reviews"] = reviews
    old_rate = cal.get("hit_rate")
    acc = review.accuracy
    if old_rate is None:
        cal["hit_rate"] = acc
    else:
        cal["hit_rate"] = round(float(old_rate) * 0.7 + acc * 0.3, 3)
    notes.append(f"滚动命中率 {cal['hit_rate']:.0%}（今日 {acc:.0%}）")

    review.calibration_after = cal
    review.optimization_notes = notes
    return cal


def apply_review_to_forecast(
    forecast: dict[str, Any],
    review: ForecastDayReview,
) -> dict[str, Any]:
    """Append review record and per-day actuals onto forecast file."""
    data = dict(forecast)
    reviews = list(data.get("reviews") or [])
    reviews.append(review.to_dict())
    data["reviews"] = reviews[-10:]

    ds = review.date
    actuals = dict(data.get("actuals") or {})
    actuals[ds] = {
        "symbols": {
            e.code: {
                "change_pct": e.actual_change_pct,
                "hit": e.hit,
                "error_pct": e.error_pct,
            }
            for e in review.symbol_evals
        },
        "accuracy": review.accuracy,
        "mss_actual": review.mss_actual,
        "mss_hit": review.mss_hit,
    }
    data["actuals"] = actuals
    data["last_review"] = review.to_dict()
    return data


def review_active_forecast(
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    trading_date: Optional[date] = None,
    mss_actual: Optional[float] = None,
) -> Optional[ForecastDayReview]:
    """Close-time hook: score today's forecast, persist, calibrate."""
    cfg = settings or {}
    wf_cfg = cfg.get("week_forecast") or {}
    if wf_cfg.get("enabled", True) is False:
        return None
    if wf_cfg.get("close_review", True) is False:
        return None

    d = trading_date or today_shanghai()
    forecast = load_active_forecast(d)
    if not forecast:
        return None

    ds = d.isoformat()
    if ds not in (forecast.get("trading_days") or []):
        return None

    already = (forecast.get("actuals") or {}).get(ds)
    if already:
        return None

    if mss_actual is None:
        mss_actual = snapshot.get("mss_final")
        if mss_actual is None:
            verify_mss = snapshot.get("mss_final")
            mss_actual = verify_mss

    review = evaluate_day_forecast(forecast, snapshot, d, mss_actual=mss_actual)
    review.kronos_review = _kronos_review_summary(forecast, review)
    cal = optimize_calibration(review, review.calibration_before, cfg)
    save_calibration(cal)

    updated = apply_review_to_forecast(forecast, review)
    if review.kronos_review:
        updated["last_kronos_review"] = review.kronos_review
    save_forecast(updated)

    review.optimization_notes = list(review.optimization_notes) + _kronos_calibration_notes(
        review.kronos_review
    )
    return review


def _kronos_review_summary(
    forecast: dict[str, Any],
    review: ForecastDayReview,
) -> dict[str, Any]:
    ds = review.date
    paths = forecast.get("kronos_paths") or {}
    if not paths:
        return {}

    errors: list[float] = []
    divergences = 0
    for ev in review.symbol_evals:
        block = paths.get(ev.code) or {}
        if not block.get("available"):
            continue
        k_day = (block.get("days") or {}).get(ds)
        if not k_day or ev.actual_change_pct is None:
            continue
        k_chg = float(k_day.get("change_pct") or 0)
        errors.append(float(ev.actual_change_pct) - k_chg)
        if k_day.get("direction") and k_day["direction"] != ev.predicted_direction:
            divergences += 1

    out: dict[str, Any] = {"divergence_count": divergences}
    if errors:
        out["mean_error_pct"] = round(sum(errors) / len(errors), 2)
    return out


def _kronos_calibration_notes(kronos_review: Optional[dict[str, Any]]) -> list[str]:
    if not kronos_review:
        return []
    notes: list[str] = []
    err = kronos_review.get("mean_error_pct")
    if err is not None and abs(float(err)) > 1.0:
        notes.append(f"Kronos 收盘偏差 {float(err):+.2f}% → 可微调 vol_scale")
    return notes


def render_forecast_review_markdown(review: ForecastDayReview) -> str:
    if not review.symbol_evals:
        return ""

    lines = ["**🔮 下周预测复盘（今日）**", ""]
    lines.append(
        f"- 标的命中率：**{review.symbol_hits}/{review.symbol_total}** "
        f"({review.accuracy:.0%})"
    )
    if review.mss_hit is not None:
        hit = "✅" if review.mss_hit else "❌"
        lines.append(
            f"- MSS {hit} 预测 {review.mss_predicted} vs 实际 {review.mss_actual}"
        )

    lines.append("")
    dir_cn = {"up": "↑", "down": "↓", "flat": "→"}
    for e in review.symbol_evals:
        mark = "✅" if e.hit else "❌"
        pred = dir_cn.get(e.predicted_direction, "→")
        actual_s = f"{e.actual_change_pct:+.2f}%" if e.actual_change_pct is not None else "—"
        lo, hi = e.predicted_range
        lines.append(
            f"- {mark} **{e.name}** 预测 {pred}[{lo:+.1f}%,{hi:+.1f}%] 实际 {actual_s}"
        )

    if review.optimization_notes:
        lines.append("")
        lines.append("**校准优化：**")
        for n in review.optimization_notes:
            lines.append(f"- {n}")

    return "\n".join(lines).strip()

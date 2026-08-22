# -*- coding: utf-8
"""AKShare historical hold-out backtest for Kronos (FaceCat backtest-style)."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from agent_reach.daily_run.kronos_predictor import (
    _direction_from_change,
    fetch_ohlcv_history,
    kronos_cfg,
    normalize_symbol,
    predict_from_ohlcv_frames,
)


def _actual_direction(prev_close: float, close: float) -> str:
    if prev_close <= 0:
        return "flat"
    chg = (close - prev_close) / prev_close * 100
    return _direction_from_change(chg)


def _compare_fold(
    predicted: dict[str, Any],
    actual_rows: Any,
    *,
    anchor_close: float,
) -> dict[str, Any]:
    """Compare one hold-out slice against Kronos prediction."""
    day_evals: list[dict[str, Any]] = []
    prev = anchor_close
    direction_hits = 0
    close_errors: list[float] = []
    change_errors: list[float] = []

    pred_days = predicted.get("days") or {}
    for i, (_, row) in enumerate(actual_rows.iterrows()):
        ts = row["timestamps"]
        ds = ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
        actual_close = float(row["close"])
        actual_chg = (actual_close - prev) / prev * 100 if prev else 0.0
        actual_dir = _actual_direction(prev, actual_close)

        pred_day = pred_days.get(ds) or {}
        pred_close = pred_day.get("close")
        pred_chg = float(pred_day.get("change_pct") or 0)
        pred_dir = pred_day.get("direction") or _direction_from_change(pred_chg)

        if pred_close is not None and actual_close:
            close_errors.append((float(pred_close) - actual_close) / actual_close * 100)
        change_errors.append(actual_chg - pred_chg)
        if pred_dir == actual_dir:
            direction_hits += 1

        day_evals.append(
            {
                "date": ds,
                "actual_close": round(actual_close, 3),
                "predicted_close": round(float(pred_close), 3) if pred_close is not None else None,
                "actual_change_pct": round(actual_chg, 2),
                "predicted_change_pct": round(pred_chg, 2),
                "actual_direction": actual_dir,
                "predicted_direction": pred_dir,
                "direction_hit": pred_dir == actual_dir,
            }
        )
        prev = actual_close

    n = len(day_evals)
    pred_cum = float(predicted.get("cum_change_pct") or 0)
    actual_cum = (prev - anchor_close) / anchor_close * 100 if anchor_close else 0.0
    return {
        "days": day_evals,
        "direction_hit_rate": round(direction_hits / n, 4) if n else None,
        "mean_abs_close_error_pct": round(sum(abs(e) for e in close_errors) / len(close_errors), 2)
        if close_errors
        else None,
        "mean_close_error_pct": round(sum(close_errors) / len(close_errors), 2) if close_errors else None,
        "mean_change_error_pct": round(sum(change_errors) / len(change_errors), 2)
        if change_errors
        else None,
        "cum_direction_match": _direction_from_change(actual_cum) == predicted.get("direction_nd"),
        "actual_cum_change_pct": round(actual_cum, 2),
        "predicted_cum_change_pct": round(pred_cum, 2),
    }


def run_kronos_holdout_backtest(
    code: str,
    *,
    holdout_days: Optional[int] = None,
    folds: int = 1,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Walk-back hold-out: for each fold, train on preceding lookback bars and
    compare Kronos predictions to realized OHLCV (AKShare qfq).
    """
    cfg = kronos_cfg(settings)
    lookback = int(cfg.get("lookback_window", 90))
    pred_window = int(cfg.get("predict_window", 10))
    holdout = min(int(holdout_days or cfg.get("holdout_days", 5)), pred_window)
    fold_count = max(1, int(folds or cfg.get("holdout_folds", 1)))
    total_bars = lookback + holdout * fold_count

    sym, _ = normalize_symbol(code)
    try:
        df = fetch_ohlcv_history(code, lookback=total_bars, settings=settings)
    except Exception as exc:
        return {
            "available": False,
            "code": code,
            "error": str(exc),
        }

    if len(df) < lookback + holdout:
        return {
            "available": False,
            "code": code,
            "error": f"历史 K 线不足：需要 ≥{lookback + holdout} 根，实际 {len(df)}",
        }

    fold_results: list[dict[str, Any]] = []
    for fold in range(fold_count):
        holdout_end = len(df) - fold * holdout
        holdout_start = holdout_end - holdout
        if holdout_start < lookback:
            break

        train = df.iloc[:holdout_start]
        actual = df.iloc[holdout_start:holdout_end]
        use_len = min(len(train), lookback)
        x_df = train.iloc[-use_len:][["open", "high", "low", "close", "volume", "amount"]]
        x_timestamp = train.iloc[-use_len:]["timestamps"]
        anchor = float(train["close"].iloc[-1])
        trading_days = [ts.date() for ts in actual["timestamps"]]

        predicted = predict_from_ohlcv_frames(
            x_df,
            x_timestamp,
            trading_days,
            base_price=anchor,
            settings=settings,
            code=code,
        )
        if not predicted or not predicted.get("available"):
            fold_results.append(
                {
                    "fold": fold + 1,
                    "holdout_start": trading_days[0].isoformat() if trading_days else "",
                    "holdout_end": trading_days[-1].isoformat() if trading_days else "",
                    "error": (predicted or {}).get("error", "Kronos 预测失败"),
                }
            )
            continue

        comparison = _compare_fold(predicted, actual, anchor_close=anchor)
        fold_results.append(
            {
                "fold": fold + 1,
                "holdout_start": trading_days[0].isoformat(),
                "holdout_end": trading_days[-1].isoformat(),
                "lookback_used": use_len,
                "predicted": predicted,
                **comparison,
            }
        )

    ok_folds = [f for f in fold_results if "direction_hit_rate" in f]
    if not ok_folds:
        return {
            "available": False,
            "code": sym,
            "holdout_days": holdout,
            "folds_requested": fold_count,
            "folds": fold_results,
            "error": fold_results[-1].get("error") if fold_results else "无有效 fold",
        }

    dir_rates = [float(f["direction_hit_rate"]) for f in ok_folds if f.get("direction_hit_rate") is not None]
    mae_close = [float(f["mean_abs_close_error_pct"]) for f in ok_folds if f.get("mean_abs_close_error_pct") is not None]
    mean_chg_err = [
        float(f["mean_change_error_pct"]) for f in ok_folds if f.get("mean_change_error_pct") is not None
    ]
    summary = {
        "direction_hit_rate": round(sum(dir_rates) / len(dir_rates), 4) if dir_rates else None,
        "mean_abs_close_error_pct": round(sum(mae_close) / len(mae_close), 2) if mae_close else None,
        "mean_change_error_pct": round(sum(mean_chg_err) / len(mean_chg_err), 2) if mean_chg_err else None,
        "cum_direction_match_rate": round(
            sum(1 for f in ok_folds if f.get("cum_direction_match")) / len(ok_folds),
            4,
        ),
        "folds_completed": len(ok_folds),
    }

    return {
        "available": True,
        "code": sym,
        "lookback_window": lookback,
        "holdout_days": holdout,
        "folds_requested": fold_count,
        "summary": summary,
        "folds": fold_results,
    }


def render_kronos_holdout_markdown(result: dict[str, Any]) -> str:
    if not result.get("available"):
        err = result.get("error") or "回测不可用"
        return f"**Kronos hold-out 回测失败**：{err}"

    summary = result.get("summary") or {}
    lines = [
        f"**Kronos hold-out 回测 · {result.get('code', '')}**",
        "",
        f"- 窗口：lookback={result.get('lookback_window')} · holdout={result.get('holdout_days')} · "
        f"folds={summary.get('folds_completed')}/{result.get('folds_requested')}",
    ]
    if summary.get("direction_hit_rate") is not None:
        lines.append(f"- 方向命中率：**{float(summary['direction_hit_rate']):.1%}**")
    if summary.get("mean_abs_close_error_pct") is not None:
        lines.append(f"- 收盘价 MAE：**{float(summary['mean_abs_close_error_pct']):.2f}%**")
    if summary.get("mean_change_error_pct") is not None:
        chg_err = float(summary["mean_change_error_pct"])
        lines.append(f"- 涨跌幅偏差：**{chg_err:+.2f}%**")
    if summary.get("cum_direction_match_rate") is not None:
        lines.append(f"- 累计方向一致：**{float(summary['cum_direction_match_rate']):.1%}**")

    for fold in result.get("folds") or []:
        if fold.get("direction_hit_rate") is None:
            continue
        lines.append("")
        lines.append(
            f"**Fold {fold.get('fold')}** {fold.get('holdout_start')} → {fold.get('holdout_end')} · "
            f"方向 {float(fold['direction_hit_rate']):.0%} · "
            f"MAE {float(fold.get('mean_abs_close_error_pct') or 0):.2f}%"
        )
        for day in (fold.get("days") or [])[:5]:
            hit = "✓" if day.get("direction_hit") else "✗"
            lines.append(
                f"  - {day['date']} {hit} 实际 {day.get('actual_change_pct'):+.1f}% "
                f"vs 预测 {day.get('predicted_change_pct'):+.1f}%"
            )
    return "\n".join(lines)

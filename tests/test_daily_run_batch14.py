# -*- coding: utf-8
"""Tests for Batch 14: Kronos AKShare hold-out backtest helper."""

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from agent_reach.daily_run.kronos_holdout_backtest import (
    render_kronos_holdout_markdown,
    run_kronos_holdout_backtest,
)


def _make_history(n: int = 100) -> pd.DataFrame:
    timestamps = pd.date_range("2025-10-01", periods=n, freq="B")
    rows = []
    for i, ts in enumerate(timestamps):
        close = 100.0 + i * 0.2
        rows.append(
            {
                "open": close - 0.1,
                "high": close + 0.3,
                "low": close - 0.3,
                "close": close,
                "volume": 1000.0 + i,
                "amount": 100000.0 + i * 10,
                "timestamps": ts,
            }
        )
    return pd.DataFrame(rows)


def test_run_kronos_holdout_backtest_single_fold():
    hist = _make_history(100)
    holdout = hist.iloc[-5:]
    trading_days = [ts.date() for ts in holdout["timestamps"]]

    def fake_predict(x_df, x_timestamp, days, **kwargs):
        days_out = {}
        prev = float(x_df["close"].iloc[-1])
        for i, d in enumerate(days):
            close = prev * 1.01
            days_out[d.isoformat()] = {
                "close": round(close, 3),
                "change_pct": 1.0,
                "direction": "up",
            }
            prev = close
        return {
            "available": True,
            "days": days_out,
            "cum_change_pct": 5.0,
            "direction_nd": "up",
        }

    with patch(
        "agent_reach.daily_run.kronos_holdout_backtest.fetch_ohlcv_history",
        return_value=hist,
    ), patch(
        "agent_reach.daily_run.kronos_holdout_backtest.predict_from_ohlcv_frames",
        side_effect=fake_predict,
    ):
        result = run_kronos_holdout_backtest(
            "688008",
            holdout_days=5,
            folds=1,
            settings={"kronos": {"lookback_window": 90, "predict_window": 10}},
        )

    assert result["available"] is True
    assert result["summary"]["folds_completed"] == 1
    assert result["summary"]["direction_hit_rate"] is not None
    fold = result["folds"][0]
    assert len(fold["days"]) == 5
    assert fold["holdout_end"] == trading_days[-1].isoformat()


def test_run_kronos_holdout_backtest_insufficient_history():
    with patch(
        "agent_reach.daily_run.kronos_holdout_backtest.fetch_ohlcv_history",
        return_value=_make_history(50),
    ):
        result = run_kronos_holdout_backtest(
            "688008",
            holdout_days=5,
            folds=1,
            settings={"kronos": {"lookback_window": 90}},
        )
    assert result["available"] is False
    assert "不足" in result["error"]


def test_run_kronos_holdout_backtest_multi_fold():
    hist = _make_history(105)

    with patch(
        "agent_reach.daily_run.kronos_holdout_backtest.fetch_ohlcv_history",
        return_value=hist,
    ), patch(
        "agent_reach.daily_run.kronos_holdout_backtest.predict_from_ohlcv_frames",
        return_value={
            "available": True,
            "days": {},
            "cum_change_pct": 1.0,
            "direction_nd": "up",
        },
    ):
        result = run_kronos_holdout_backtest(
            "688008",
            holdout_days=5,
            folds=2,
            settings={"kronos": {"lookback_window": 90, "predict_window": 10}},
        )

    assert result["available"] is True
    assert result["summary"]["folds_completed"] == 2


def test_render_kronos_holdout_markdown():
    md = render_kronos_holdout_markdown(
        {
            "available": True,
            "code": "688008",
            "lookback_window": 90,
            "holdout_days": 5,
            "folds_requested": 1,
            "summary": {
                "direction_hit_rate": 0.8,
                "mean_abs_close_error_pct": 1.2,
                "mean_change_error_pct": -0.3,
                "cum_direction_match_rate": 1.0,
                "folds_completed": 1,
            },
            "folds": [
                {
                    "fold": 1,
                    "holdout_start": "2026-04-01",
                    "holdout_end": "2026-04-05",
                    "direction_hit_rate": 0.8,
                    "mean_abs_close_error_pct": 1.2,
                    "days": [
                        {
                            "date": "2026-04-01",
                            "actual_change_pct": 1.5,
                            "predicted_change_pct": 1.0,
                            "direction_hit": True,
                        }
                    ],
                }
            ],
        }
    )
    assert "hold-out 回测" in md
    assert "方向命中率" in md
    assert "688008" in md


def test_predict_from_ohlcv_frames_reused_by_predict_symbol_paths():
    from agent_reach.daily_run.kronos_predictor import predict_symbol_paths

    pred_df = pd.DataFrame(
        {
            "open": [101.0],
            "high": [102.0],
            "low": [100.5],
            "close": [101.5],
            "volume": [1100.0],
            "amount": [110000.0],
        }
    )
    with patch("agent_reach.daily_run.kronos_predictor.get_kronos_predictor") as mock_pred, patch(
        "agent_reach.daily_run.kronos_predictor.fetch_ohlcv_history"
    ) as mock_hist, patch(
        "agent_reach.daily_run.kronos_predictor.predict_from_ohlcv_frames"
    ) as mock_frames:
        mock_hist.return_value = _make_history(95)
        mock_frames.return_value = {"available": True, "days": {}, "cum_change_pct": 1.0}
        predict_symbol_paths(
            "688008",
            [date(2026, 7, 13)],
            settings={"kronos": {"enabled": True, "daily_cache": False}},
        )
        mock_frames.assert_called_once()
        mock_pred.assert_not_called()

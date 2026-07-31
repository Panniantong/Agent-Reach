# -*- coding: utf-8
"""Tests for Kronos predictor integration."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from agent_reach.daily_run.kronos_predictor import (
    blend_symbol_days_with_kronos,
    is_kronos_enabled,
    predict_symbol_paths,
)
from agent_reach.daily_run.plugins.technical_expert import TechnicalExpert
from agent_reach.daily_run.plugins.base import PluginContext
from agent_reach.daily_run.week_forecast import generate_week_forecast


@pytest.fixture
def portfolio():
    return {
        "total": 100000,
        "holdings": [{"code": "688008", "name": "澜起科技", "shares": 100, "cost": 250.0}],
        "watchlist": [{"code": "603986", "name": "兆易创新"}],
    }


@pytest.fixture
def snapshot(portfolio):
    return {
        "code": "688008",
        "name": "澜起科技",
        "price": 260.0,
        "change_pct": 1.5,
        "position_20d": 0.55,
        "portfolio": portfolio,
        "watchlist": portfolio["watchlist"],
    }


KRONOS_MOCK = {
    "available": True,
    "backend": "NeoQuasar/Kronos-small",
    "code": "688008",
    "lookback_used": 90,
    "predict_window": 2,
    "direction_nd": "up",
    "cum_change_pct": 2.5,
    "confidence_band": [-0.5, 1.8],
    "sample_count": 5,
    "days": {
        "2026-07-13": {"close": 265.0, "change_pct": 1.2, "direction": "up"},
        "2026-07-14": {"close": 268.0, "change_pct": 1.1, "direction": "up"},
    },
}


class TestKronosPredictor:
    def test_is_kronos_enabled(self):
        assert not is_kronos_enabled({})
        assert is_kronos_enabled({"kronos": {"enabled": True}})

    def test_blend_symbol_days(self):
        symbol = {
            "code": "688008",
            "days": {
                "2026-07-13": {
                    "direction": "flat",
                    "change_pct_range": [-1.0, 1.0],
                    "expected_change_pct": 0.0,
                    "confidence": 0.5,
                }
            },
        }
        blended = blend_symbol_days_with_kronos(symbol, KRONOS_MOCK, blend_weight=0.5)
        day = blended["days"]["2026-07-13"]
        assert day["blended"] is True
        assert day["kronos_change_pct"] == 1.2
        assert blended["kronos"]["available"] is True

    @patch("agent_reach.daily_run.week_forecast.predict_symbol_paths")
    @patch("agent_reach.daily_run.week_forecast.run_news_research", return_value=[])
    @patch("agent_reach.daily_run.week_forecast.list_trading_days")
    def test_week_forecast_with_kronos(
        self, mock_days, mock_news, mock_kronos, portfolio, snapshot
    ):
        mock_days.return_value = [date(2026, 7, 13), date(2026, 7, 14)]
        mock_kronos.return_value = KRONOS_MOCK

        forecast = generate_week_forecast(
            snapshot,
            {
                "week_forecast": {"exa_news_research": False},
                "kronos": {"enabled": True},
            },
            as_of=date(2026, 7, 12),
            portfolio=portfolio,
        )
        data = forecast.to_dict()
        assert "688008" in data["kronos_paths"]
        sym = data["symbols"]["688008"]
        assert sym["days"]["2026-07-13"].get("kronos_change_pct") == 1.2

    @patch("agent_reach.daily_run.kronos_predictor.get_kronos_predictor")
    @patch("agent_reach.daily_run.kronos_predictor.fetch_ohlcv_history")
    def test_predict_symbol_paths_success(self, mock_hist, mock_pred):
        import pandas as pd

        mock_hist.return_value = pd.DataFrame(
            {
                "open": [100.0] * 95,
                "high": [101.0] * 95,
                "low": [99.0] * 95,
                "close": [100.0] * 95,
                "volume": [1000.0] * 95,
                "amount": [100000.0] * 95,
                "timestamps": pd.date_range("2026-01-01", periods=95, freq="D"),
            }
        )
        pred_df = pd.DataFrame(
            {
                "open": [101.0, 102.0],
                "high": [102.0, 103.0],
                "low": [100.0, 101.0],
                "close": [101.5, 102.5],
                "volume": [1100.0, 1200.0],
                "amount": [110000.0, 120000.0],
            },
            index=pd.date_range("2026-07-13", periods=2, freq="D"),
        )
        predictor = MagicMock()
        predictor.predict.return_value = pred_df
        mock_pred.return_value = predictor

        result = predict_symbol_paths(
            "688008",
            [date(2026, 7, 13), date(2026, 7, 14)],
            base_price=100.0,
            settings={"kronos": {"enabled": True}},
        )
        assert result is not None
        assert result["available"] is True
        assert result["days"]["2026-07-13"]["change_pct"] == pytest.approx(1.5, abs=0.01)


class TestTechnicalKronos:
    def test_kronos_opposes_ma20(self):
        expert = TechnicalExpert()
        ctx = PluginContext(
            snapshot={
                "price": 110.0,
                "ma20": 100.0,
                "position_20d": 0.5,
                "volume_ratio": 1.2,
                "kronos": KRONOS_MOCK,
            },
            settings={"kronos": {"enabled": True}, "thresholds": {}},
        )
        result = expert.run(ctx)
        assert "Kronos" in result.summary
        assert result.score >= 50

    def test_kronos_down_vs_ma20_bull(self):
        down_kronos = {**KRONOS_MOCK, "direction_nd": "down", "cum_change_pct": -3.0}
        expert = TechnicalExpert()
        ctx = PluginContext(
            snapshot={
                "price": 110.0,
                "ma20": 100.0,
                "position_20d": 0.5,
                "volume_ratio": 1.2,
                "kronos": down_kronos,
            },
            settings={
                "kronos": {"enabled": True, "technical_max_score_delta": 12},
                "thresholds": {},
            },
        )
        base_ctx = PluginContext(
            snapshot={
                "price": 110.0,
                "ma20": 100.0,
                "position_20d": 0.5,
                "volume_ratio": 1.2,
            },
            settings={"kronos": {"enabled": False}, "thresholds": {}},
        )
        with_k = expert.run(ctx)
        without = expert.run(base_ctx)
        assert with_k.score < without.score

# -*- coding: utf-8
"""Tests for next-week forecast and daily close review calibration."""

import json
from datetime import date
from unittest.mock import patch

import pytest

from agent_reach.daily_run.week_forecast import (
    generate_week_forecast,
    load_active_forecast,
    load_calibration,
    next_trading_week_range,
    persist_week_forecast,
    render_forecast_markdown,
    save_calibration,
)
from agent_reach.daily_run.week_forecast_tracker import (
    evaluate_day_forecast,
    optimize_calibration,
    render_forecast_review_markdown,
    review_active_forecast,
)


@pytest.fixture
def portfolio():
    return {
        "total": 100000,
        "holdings": [
            {"code": "688008", "name": "澜起科技", "shares": 100, "cost": 250.0},
        ],
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
        "mss_breakdown": {"fx": 40, "flow": 50, "global": 45, "sentiment": 48},
        "macro_summary": "存储链分化",
        "portfolio": portfolio,
        "watchlist": portfolio["watchlist"],
        "sources": {"flow": {"summary": "北向净流入"}},
    }


class TestWeekForecast:
    def test_next_trading_week_from_sunday(self):
        sun = date(2026, 7, 12)
        mon, fri = next_trading_week_range(sun)
        assert mon == date(2026, 7, 13)
        assert fri == date(2026, 7, 17)

    @patch("agent_reach.daily_run.week_forecast.run_news_research", return_value=[])
    @patch("agent_reach.daily_run.week_forecast.list_trading_days")
    def test_generate_week_forecast(self, mock_days, mock_news, snapshot, portfolio):
        mock_days.return_value = [
            date(2026, 7, 13),
            date(2026, 7, 14),
            date(2026, 7, 15),
        ]
        forecast = generate_week_forecast(
            snapshot,
            {"week_forecast": {"exa_news_research": False}},
            as_of=date(2026, 7, 12),
            portfolio=portfolio,
        )
        assert len(forecast.symbols) == 2
        assert "688008" in forecast.symbols
        assert "603986" in forecast.symbols
        md = render_forecast_markdown(forecast)
        assert "下周预测" in md or "预测周期" in md
        assert "澜起科技" in md

    @patch("agent_reach.daily_run.week_forecast.run_news_research", return_value=[])
    @patch("agent_reach.daily_run.week_forecast.list_trading_days")
    def test_persist_and_load_active(self, mock_days, mock_news, snapshot, portfolio, tmp_path, monkeypatch):
        mock_days.return_value = [date(2026, 7, 13), date(2026, 7, 14)]
        monkeypatch.setattr(
            "agent_reach.daily_run.week_forecast.forecasts_dir",
            lambda: tmp_path,
        )
        forecast = generate_week_forecast(
            snapshot,
            {"week_forecast": {}},
            as_of=date(2026, 7, 12),
            portfolio=portfolio,
        )
        persist_week_forecast(forecast)
        loaded = load_active_forecast(date(2026, 7, 13))
        assert loaded is not None
        assert loaded["week_start"] == "2026-07-13"


class TestForecastTracker:
    def test_evaluate_day_forecast_hit(self):
        forecast = {
            "symbols": {
                "688008": {
                    "name": "澜起科技",
                    "role": "holding",
                    "days": {
                        "2026-07-13": {
                            "direction": "up",
                            "change_pct_range": [0.0, 3.0],
                            "expected_change_pct": 1.5,
                        }
                    },
                }
            },
            "mss_daily": {"2026-07-13": {"range": [40, 55]}},
        }
        snap = {
            "portfolio": {"holdings": [{"code": "688008", "name": "澜起", "change_pct": 1.2}]},
            "code": "688008",
            "change_pct": 1.2,
        }
        review = evaluate_day_forecast(
            forecast, snap, date(2026, 7, 13), mss_actual=48.0
        )
        assert review.symbol_total == 1
        assert review.symbol_hits == 1
        assert review.mss_hit is True

    def test_optimize_calibration(self):
        from agent_reach.daily_run.week_forecast_tracker import ForecastDayReview, SymbolEval

        review = ForecastDayReview(
            date="2026-07-13",
            symbol_evals=[
                SymbolEval(
                    code="688008",
                    name="澜起",
                    role="holding",
                    predicted_direction="up",
                    predicted_range=[0, 2],
                    actual_change_pct=2.5,
                    hit=False,
                    error_pct=1.0,
                )
            ],
            symbol_hits=0,
            symbol_total=1,
            accuracy=0.0,
            calibration_before={"bias_pct": 0.0, "vol_scale": 1.0, "reviews": 0},
        )
        cal = optimize_calibration(review, review.calibration_before, {"week_forecast": {}})
        assert cal["reviews"] == 1
        assert "hit_rate" in cal
        assert review.optimization_notes

    def test_review_active_forecast_end_to_end(
        self, snapshot, portfolio, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "agent_reach.daily_run.week_forecast.forecasts_dir",
            lambda: tmp_path,
        )
        cal_path = tmp_path / "calibration.json"
        monkeypatch.setattr(
            "agent_reach.daily_run.week_forecast.calibration_path",
            lambda: cal_path,
        )

        forecast_data = {
            "week_start": "2026-07-13",
            "week_end": "2026-07-17",
            "trading_days": ["2026-07-13"],
            "symbols": {
                "688008": {
                    "name": "澜起科技",
                    "role": "holding",
                    "days": {
                        "2026-07-13": {
                            "direction": "up",
                            "change_pct_range": [-1, 3],
                            "expected_change_pct": 1.0,
                        }
                    },
                }
            },
            "mss_daily": {"2026-07-13": {"range": [40, 55]}},
            "reviews": [],
        }
        (tmp_path / "2026-07-13.json").write_text(
            json.dumps(forecast_data, ensure_ascii=False), encoding="utf-8"
        )

        snap = dict(snapshot)
        snap["change_pct"] = 1.8
        snap["mss_final"] = 50

        review = review_active_forecast(
            snap,
            settings={"week_forecast": {"enabled": True, "close_review": True}},
            trading_date=date(2026, 7, 13),
            mss_actual=50,
        )
        assert review is not None
        assert review.symbol_hits == 1
        md = render_forecast_review_markdown(review)
        assert "预测复盘" in md

        cal = load_calibration()
        assert cal.get("reviews") == 1

        review2 = review_active_forecast(
            snap,
            settings={"week_forecast": {}},
            trading_date=date(2026, 7, 13),
        )
        assert review2 is None


class TestScheduleForecast:
    @patch("agent_reach.daily_run.workflows.run_forecast")
    @patch("agent_reach.daily_run.snapshot_builder.build_and_save")
    @patch("agent_reach.daily_run.snapshot_builder.load_portfolio")
    def test_run_scheduled_forecast(self, mock_load, mock_build, mock_run_forecast, portfolio, tmp_path):
        from agent_reach.daily_run.schedule import run_scheduled

        mock_load.return_value = portfolio
        mock_build.return_value = ({"code": "688008"}, tmp_path / "snap.json")
        mock_run_forecast.return_value = {
            "steps": ["generate", "persist", "render"],
            "forecast": {"week_start": "2026-07-13"},
            "forecast_path": str(tmp_path / "2026-07-13.json"),
            "markdown": "forecast",
        }

        with patch("agent_reach.daily_run.trade_calendar.is_trading_day", return_value=(False, "周末")):
            result = run_scheduled("forecast", push=False)

        assert result["job"] == "forecast"
        assert not result.get("skipped")
        mock_run_forecast.assert_called_once()

    def test_crontab_has_forecast_sunday(self):
        from agent_reach.daily_run.schedule import render_crontab_block

        block = render_crontab_block()
        assert "daily-run-local-cron.sh forecast" in block
        assert "30 8 * * 0" in block

# -*- coding: utf-8
"""Tests for Batch 13: Kronos calendar/OHLCV + week_forecast Exa cache."""

from datetime import date
from unittest.mock import patch

import pytest

from agent_reach.daily_run.intent_cache import clear_intent_cache
from agent_reach.daily_run.kronos_predictor import (
    attach_kronos_to_snapshot,
    render_kronos_path_markdown,
    resolve_kronos_trading_days,
)
from agent_reach.daily_run.week_forecast import run_news_research


def test_resolve_kronos_trading_days_skips_weekend():
    with patch(
        "agent_reach.daily_run.trade_calendar.next_trading_day",
        side_effect=[date(2026, 7, 13), date(2026, 7, 14), date(2026, 7, 15)],
    ):
        days = resolve_kronos_trading_days(
            3,
            settings={"kronos": {"use_trade_calendar": True}},
            as_of=date(2026, 7, 10),
        )
    assert days == [date(2026, 7, 13), date(2026, 7, 14), date(2026, 7, 15)]


def test_attach_kronos_uses_trade_calendar():
    snap = {"code": "688008", "price": 100.0}
    kronos_result = {"available": True, "days": {}, "cum_change_pct": 1.0, "direction_nd": "up"}
    with patch(
        "agent_reach.daily_run.kronos_predictor.resolve_kronos_trading_days",
        return_value=[date(2026, 7, 13), date(2026, 7, 14)],
    ) as mock_days, patch(
        "agent_reach.daily_run.kronos_predictor.predict_symbol_paths",
        return_value=kronos_result,
    ):
        out = attach_kronos_to_snapshot(snap, settings={"kronos": {"enabled": True}})
    mock_days.assert_called_once()
    assert out["kronos"]["available"] is True


def test_predict_symbol_paths_persists_ohlcv():
    import pandas as pd

    from agent_reach.daily_run.kronos_predictor import predict_symbol_paths

    pred_df = pd.DataFrame(
        {
            "open": [101.0, 102.0],
            "high": [102.5, 103.5],
            "low": [100.5, 101.5],
            "close": [101.5, 102.5],
            "volume": [1100.0, 1200.0],
            "amount": [110000.0, 120000.0],
        }
    )
    with patch("agent_reach.daily_run.kronos_predictor.get_kronos_predictor") as mock_pred, patch(
        "agent_reach.daily_run.kronos_predictor.fetch_ohlcv_history"
    ) as mock_hist:
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
        predictor = mock_pred.return_value
        predictor.predict.return_value = pred_df
        result = predict_symbol_paths(
            "688008",
            [date(2026, 7, 13), date(2026, 7, 14)],
            base_price=100.0,
            settings={"kronos": {"enabled": True, "daily_cache": False}},
        )
    day = result["days"]["2026-07-13"]
    assert day["open"] == pytest.approx(101.0)
    assert day["high"] == pytest.approx(102.5)
    assert day["low"] == pytest.approx(100.5)
    assert result["band_kind"] == "ohlc_cumulative"
    assert result["confidence_band"][1] >= result["confidence_band"][0]


def test_render_kronos_path_markdown():
    md = render_kronos_path_markdown(
        {
            "available": True,
            "direction_nd": "up",
            "cum_change_pct": 2.5,
            "confidence_band": [0.5, 3.2],
            "band_kind": "ohlc_cumulative",
            "sample_count": 5,
            "days": {
                "2026-07-13": {
                    "direction": "up",
                    "change_pct": 1.2,
                    "open": 100.0,
                    "high": 102.0,
                    "low": 99.5,
                    "close": 101.2,
                }
            },
        }
    )
    assert "虚 K 路径" in md
    assert "O100.0" in md
    assert "ohlc_cumulative" in md


def test_run_news_research_uses_intent_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.intent_cache.intent_cache_dir",
        lambda: tmp_path / "intent_cache",
    )
    clear_intent_cache()
    calls = {"n": 0}

    def fake_exa(query, **kwargs):
        calls["n"] += 1
        return [{"title": "hit", "url": "https://example.com", "text": "body"}]

    with patch("agent_reach.daily_run.exa_client.is_exa_available", return_value=True), patch(
        "agent_reach.daily_run.exa_client.web_search_exa",
        side_effect=fake_exa,
    ), patch(
        "agent_reach.daily_run.exa_client.summarize_hits",
        return_value="summary text",
    ):
        settings = {
            "week_forecast": {"exa_news_research": True, "max_news_queries": 1},
            "intent": {"enabled": True, "ttl_seconds": 600},
        }
        queries = [{"type": "news", "query": "China A-share outlook", "label": "宏观"}]
        first = run_news_research(queries, settings)
        second = run_news_research(queries, settings)

    assert calls["n"] == 1
    assert first[0]["success"] is True
    assert second[0].get("from_cache") is True
    clear_intent_cache()

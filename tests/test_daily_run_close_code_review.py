# -*- coding: utf-8
"""Tests for close code walkthrough and bug fixes."""

from agent_reach.daily_run.close_code_review import (
    render_code_review_markdown,
    run_close_code_review,
)
from agent_reach.daily_run.settings import load_settings


def test_auto_fix_watchlist_overlap():
    settings = load_settings()
    portfolio = {
        "total": 100000,
        "cash": 61000,
        "cash_ratio": 0.61,
        "holdings": [{"code": "688008", "name": "澜起科技", "shares": 100, "days_held": 5}],
        "watchlist": [
            {"code": "688008", "name": "澜起科技"},
            {"code": "603986", "name": "兆易创新"},
        ],
    }
    snapshot = {"mss_final": 48, "watchlist": portfolio["watchlist"]}

    result = run_close_code_review(
        portfolio=portfolio,
        snapshot=snapshot,
        settings=settings,
    )
    assert result.portfolio_changed is True
    codes = {w["code"] for w in result.portfolio["watchlist"]}
    assert "688008" not in codes
    assert any("重复" in f for f in result.fixes_applied)


def test_render_code_review_markdown():
    settings = load_settings()
    result = run_close_code_review(
        portfolio={"holdings": [], "watchlist": [], "cash": 1, "total": 1, "cash_ratio": 1},
        snapshot={},
        settings=settings,
    )
    md = render_code_review_markdown(result)
    assert "代码走读" in md


def test_detect_cash_ratio_mismatch():
    settings = load_settings()
    portfolio = {
        "total": 100000,
        "cash": 50000,
        "cash_ratio": 0.61,
        "holdings": [],
        "watchlist": [],
    }
    result = run_close_code_review(portfolio=portfolio, snapshot={}, settings=settings)
    assert result.portfolio_changed is True
    assert abs(result.portfolio["cash_ratio"] - 0.5) < 0.001


def test_auto_fix_stale_days_held():
    from datetime import date
    from unittest.mock import patch

    settings = load_settings()
    portfolio = {
        "total": 100000,
        "cash": 50000,
        "cash_ratio": 0.5,
        "holdings": [
            {
                "code": "000725",
                "name": "京东方A",
                "shares": 1000,
                "cost": 6.0,
                "acquired_date": "2026-07-24",
                "days_held": 0,
            }
        ],
        "watchlist": [],
    }
    with patch(
        "agent_reach.daily_run.trade_calendar.today_shanghai",
        return_value=date(2026, 7, 27),
    ):
        result = run_close_code_review(portfolio=portfolio, snapshot={}, settings=settings)
    assert result.portfolio_changed is True
    assert result.portfolio["holdings"][0]["days_held"] == 1
    assert any("days_held" in f for f in result.fixes_applied)


def test_duplicate_scan_ids_reported():
    settings = load_settings()
    settings.setdefault("close_code_review", {})["walk_on_close"] = False
    settings["close_code_review"]["run_smoke_tests"] = False
    result = run_close_code_review(
        portfolio={"holdings": [], "watchlist": [], "cash": 1, "total": 1, "cash_ratio": 1},
        snapshot={},
        settings=settings,
        scans=[
            {"scan_id": "S1", "mss_final": 50},
            {"scan_id": "S1", "mss_final": 49},
        ],
    )
    assert any("重复" in f.title for f in result.findings)


def test_code_review_disabled_skips_findings():
    settings = load_settings()
    settings["close_code_review"] = {"enabled": False}
    portfolio = {
        "total": 100000,
        "cash": 61000,
        "cash_ratio": 0.99,
        "holdings": [],
        "watchlist": [{"code": "688008", "name": "澜起科技"}],
    }
    result = run_close_code_review(portfolio=portfolio, snapshot={}, settings=settings)
    assert result.findings == []
    assert result.portfolio_changed is False


def test_auto_fix_abnormal_cost():
    settings = load_settings()
    portfolio = {
        "total": 100000,
        "cash": 50000,
        "cash_ratio": 0.5,
        "holdings": [{"code": "002583", "name": "海能达", "shares": 1000, "cost": 28.4}],
        "watchlist": [],
    }
    snapshot = {
        "code": "002583",
        "portfolio": {
            "holdings": [
                {"code": "002583", "price": 7.98, "quote_source": "xueqiu"},
            ]
        },
    }
    result = run_close_code_review(portfolio=portfolio, snapshot=snapshot, settings=settings)
    assert result.portfolio_changed is True
    assert result.portfolio["holdings"][0]["cost"] == 7.98
    assert any("cost" in f.lower() or "成本" in f for f in result.fixes_applied)


def test_harness_overlay_missing_when_runtime_absent():
    settings = load_settings()
    settings.setdefault("harness", {})["enabled"] = True
    settings["harness"]["threshold_evolution_mode"] = "harness"
    settings.pop("harness_runtime", None)
    result = run_close_code_review(
        portfolio={"holdings": [], "watchlist": [], "cash": 1, "total": 1, "cash_ratio": 1},
        snapshot={},
        settings=settings,
    )
    assert any(f.area == "harness" and "overlay" in f.title for f in result.findings)


def test_harness_defensive_signal_threshold_mismatch(monkeypatch):
    settings = load_settings()
    from agent_reach.daily_run.settings import effective_settings

    settings = effective_settings(settings)
    settings["thresholds"]["macro_veto"] = 40.0
    settings.setdefault("harness_runtime", {})["trade_signals"] = {
        "defensive_trim": True,
        "mss_forecast_miss": True,
        "deviation_active": True,
    }
    monkeypatch.setattr(
        "agent_reach.daily_run.harness_policy.resolve_harness_trade_signals",
        lambda *args, **kwargs: {
            "defensive_trim": True,
            "mss_forecast_miss": True,
            "deviation_active": True,
            "kronos_bullish": {},
            "kronos_bearish": {},
        },
    )
    result = run_close_code_review(
        portfolio={"holdings": [], "watchlist": [], "cash": 1, "total": 1, "cash_ratio": 1},
        snapshot={},
        settings=settings,
    )
    assert any(f.area == "harness" and "macro_veto" in f.title for f in result.findings)

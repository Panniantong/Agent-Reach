# -*- coding: utf-8
"""Tests for watchlist adjust (morning/close only)."""

import json

import pytest

from agent_reach.daily_run.trade_calendar import today_shanghai

from agent_reach.daily_run.portfolio_manager import apply_auto_adjust
from agent_reach.daily_run.intraday import TradeDecision
from agent_reach.daily_run.settings import load_settings
from agent_reach.daily_run.watchlist_manager import (
    adjust_watchlist,
    can_adjust_watchlist,
    collect_intraday_sold_codes,
)


@pytest.fixture
def portfolio():
    return {
        "total": 100000,
        "cash": 61000,
        "holdings": [{"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87}],
        "watchlist": [
            {"code": "603986", "name": "兆易创新"},
            {"code": "002273", "name": "水晶光电"},
        ],
    }


@pytest.fixture
def snapshot(portfolio):
    return {
        "mss_final": 48.0,
        "mss_breakdown": {"fx": 47, "flow": 48, "global": 46, "sentiment": 53},
        "watchlist": [
            {"code": "603986", "name": "兆易创新", "price": 603.17, "change_pct": -2.71},
            {"code": "002273", "name": "水晶光电", "price": 32.04, "change_pct": -6.23},
        ],
        "portfolio": {
            "holdings": [
                {"code": "688008", "name": "澜起科技", "price": 247.15, "change_pct": -2.39},
            ],
        },
    }


@pytest.fixture
def settings():
    s = load_settings()
    s.setdefault("watchlist", {})
    s["watchlist"]["auto_adjust_enabled"] = True
    s["watchlist"]["min_size"] = 0
    s["watchlist"]["hot_topic_adjust_enabled"] = False
    s["watchlist"]["hot_topic_fetch_if_missing"] = False
    return s


class TestWatchlistPolicy:
    def test_can_adjust_phases(self):
        assert can_adjust_watchlist("morning") is True
        assert can_adjust_watchlist("close") is True
        assert can_adjust_watchlist("intraday") is False

    def test_intraday_sell_does_not_touch_watchlist(self, portfolio, snapshot):
        settings = load_settings()
        settings["portfolio"] = {"auto_adjust_enabled": True, "max_holdings": 10}
        portfolio["holdings"].append(
            {"code": "002273", "name": "水晶光电", "shares": 300, "cost": 33.81, "days_held": 5}
        )
        snapshot["portfolio"]["holdings"].append(
            {"code": "002273", "name": "水晶光电", "price": 32.04, "change_pct": -6.23}
        )
        before = len(portfolio["watchlist"])
        decision = TradeDecision(
            action="sell",
            trade_id="T1",
            lookback_mss=35.0,
            lookback_detail=[],
            trend="falling",
            reasoning="卖",
        )
        result = apply_auto_adjust(portfolio, decision, snapshot, settings, allow_watchlist_changes=False)
        assert result.applied is True
        assert len(result.portfolio["watchlist"]) == before

    def test_morning_removes_held_from_watchlist(self, portfolio, snapshot, settings):
        portfolio["watchlist"].append({"code": "688008", "name": "澜起科技"})
        result = adjust_watchlist(portfolio, snapshot, settings, "morning")
        assert result.applied is True
        codes = {w["code"] for w in result.portfolio["watchlist"]}
        assert "688008" not in codes

    def test_close_recycles_sold(self, portfolio, snapshot, settings, tmp_path, monkeypatch):
        from agent_reach.daily_run import portfolio_manager

        ledger = tmp_path / "ledger.jsonl"
        today = today_shanghai().isoformat()
        sold_at = f"{today}T10:00:00+00:00"
        ledger.write_text(
            json.dumps(
                {
                    "at": sold_at,
                    "actions": [{"side": "sell", "code": "002273", "name": "水晶光电"}],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(portfolio_manager, "default_ledger_path", lambda: ledger)
        portfolio["watchlist"] = [{"code": "603986", "name": "兆易创新"}]
        result = adjust_watchlist(
            portfolio,
            snapshot,
            settings,
            "close",
            sold_codes=collect_intraday_sold_codes(settings),
        )
        codes = {w["code"] for w in result.portfolio["watchlist"]}
        assert "002273" in codes

    def test_close_trims_watchlist_to_total_cap(self, portfolio, snapshot, settings):
        settings.setdefault("portfolio", {})
        settings["portfolio"]["max_total_symbols"] = 3
        portfolio["watchlist"] = [
            {"code": "603986", "name": "兆易创新"},
            {"code": "002273", "name": "水晶光电"},
            {"code": "000725", "name": "京东方A"},
        ]
        result = adjust_watchlist(portfolio, snapshot, settings, "close")
        wl_only = {
            w["code"]
            for w in result.portfolio["watchlist"]
            if w["code"] not in {h["code"] for h in portfolio["holdings"]}
        }
        assert len(portfolio["holdings"]) + len(wl_only) <= 3

    def test_intraday_phase_rejected(self, portfolio, snapshot, settings):
        result = adjust_watchlist(portfolio, snapshot, settings, "intraday")  # type: ignore[arg-type]
        assert result.applied is False

    def test_close_macro_avoid_trims_watchlist(self, portfolio, snapshot, settings):
        portfolio["watchlist"] = [
            {"code": "603986", "name": "兆易创新"},
            {"code": "002273", "name": "水晶光电"},
            {"code": "000725", "name": "京东方A"},
            {"code": "002415", "name": "海康威视"},
            {"code": "600519", "name": "贵州茅台"},
        ]
        result = adjust_watchlist(
            portfolio,
            snapshot,
            settings,
            "close",
            verify={"verdict_current": "回避"},
        )
        assert result.applied is True
        assert len(result.portfolio["watchlist"]) <= 3

    def test_collect_intraday_sold_codes_uses_shanghai_date(
        self, settings, tmp_path, monkeypatch
    ):
        from agent_reach.daily_run import portfolio_manager

        ledger = tmp_path / "ledger.jsonl"
        today = today_shanghai().isoformat()
        ledger.write_text(
            json.dumps(
                {
                    "at": f"{today}T10:00:00+08:00",
                    "actions": [{"side": "sell", "code": "002273", "name": "水晶光电"}],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(portfolio_manager, "default_ledger_path", lambda: ledger)
        sold = collect_intraday_sold_codes(settings)
        assert len(sold) == 1
        assert sold[0]["code"] == "002273"

    def test_render_watchlist_adjust_markdown(self, portfolio, snapshot, settings):
        from agent_reach.daily_run.watchlist_manager import render_watchlist_adjust_markdown

        portfolio["watchlist"].append({"code": "688008", "name": "澜起科技"})
        result = adjust_watchlist(portfolio, snapshot, settings, "morning")
        md = render_watchlist_adjust_markdown(result)
        assert "观察池" in md
        assert "688008" in md or "澜起" in md

    def test_close_reorders_by_change_pct(self, portfolio, snapshot, settings):
        settings["watchlist"]["close_reorder_by_performance"] = True
        settings["watchlist"]["min_size"] = 0
        snapshot["watchlist"] = [
            {"code": "603986", "name": "兆易创新", "change_pct": -2.71},
            {"code": "002273", "name": "水晶光电", "change_pct": 1.5},
        ]
        portfolio["watchlist"] = [
            {"code": "603986", "name": "兆易创新"},
            {"code": "002273", "name": "水晶光电"},
        ]
        result = adjust_watchlist(portfolio, snapshot, settings, "close")
        codes = [w["code"] for w in result.portfolio["watchlist"]]
        assert codes[0] == "002273"

    def test_close_fills_to_min_size(self, portfolio, snapshot, settings):
        settings["watchlist"]["min_size"] = 5
        settings["watchlist"]["max_size"] = 10
        settings["watchlist"]["candidates"] = [
            {"code": "000725", "name": "京东方A", "keywords": ["京东方"]},
            {"code": "002415", "name": "海康威视", "keywords": ["海康"]},
            {"code": "600584", "name": "长电科技", "keywords": ["长电"]},
            {"code": "688012", "name": "中微公司", "keywords": ["中微"]},
        ]
        portfolio["watchlist"] = [{"code": "603986", "name": "兆易创新"}]
        result = adjust_watchlist(portfolio, snapshot, settings, "close")
        assert len(result.portfolio["watchlist"]) >= 5

    def test_close_hot_topic_add_and_remove(self, portfolio, snapshot, settings):
        settings["watchlist"]["min_size"] = 0
        settings["watchlist"]["hot_topic_adjust_enabled"] = True
        settings["watchlist"]["hot_topic_fetch_if_missing"] = False
        settings["watchlist"]["candidates"] = [
            {"code": "000725", "name": "京东方A", "keywords": ["京东方", "面板"]},
        ]
        snapshot["hot_topics_matched"] = [{"title": "面板产业链涨价，京东方受益"}]
        snapshot["watchlist"] = [
            {"code": "603986", "name": "兆易创新", "change_pct": -4.0},
            {"code": "002273", "name": "水晶光电", "change_pct": -6.23},
        ]
        portfolio["watchlist"] = [
            {"code": "603986", "name": "兆易创新"},
            {"code": "002273", "name": "水晶光电"},
        ]
        result = adjust_watchlist(portfolio, snapshot, settings, "close")
        codes = {w["code"] for w in result.portfolio["watchlist"]}
        assert "000725" in codes
        assert "603986" not in codes or any(
            c.action == "remove" and c.code == "603986" for c in result.changes
        )

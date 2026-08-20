# -*- coding: utf-8
"""Tests for close sell-rules what-if comparison."""

from datetime import date
from unittest.mock import patch

import pytest

from agent_reach.daily_run.quote_fetch import QuoteFetchResult
from agent_reach.daily_run.sell_rules_whatif import (
    build_sell_rules_whatif,
    build_weekly_sell_rules_whatif,
    render_sell_rules_whatif_markdown,
    summarize_whatif_for_harness,
)


def _settings_partial_sell():
    return {
        "harness_runtime": {
            "deep_loss_policy": {
                "sell_ratio": 0.35,
                "non_deep_loss_sell_ratio": 0.5,
                "cover_ratio": 1.2,
                "loss_cny_threshold": 5000,
                "loss_pct_threshold": 10,
            },
        },
        "pnl_overview": {},
        "portfolio": {"auto_adjust_enabled": True},
        "trading": {"holding_lock_days": 0},
    }


@pytest.fixture(autouse=True)
def _no_capital_flow(monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.capital_events.net_capital_flow",
        lambda day, path=None: 0.0,
    )


@pytest.fixture
def harness_tmp(monkeypatch, tmp_path):
    hdir = tmp_path / "harness"
    monkeypatch.setattr("agent_reach.daily_run.harness.harness_dir", lambda: hdir)
    monkeypatch.setattr("agent_reach.daily_run.harness._state_path", lambda: hdir / "harness_state.json")
    monkeypatch.setattr(
        "agent_reach.daily_run.harness._refinements_path",
        lambda: hdir / "refinements.jsonl",
    )
    return hdir


class TestSellRulesWhatIf:
    def test_partial_sell_vs_full_clear(self):
        """Non-deep holdings: 50% ratio vs 100% actual sell."""
        morning = {
            "portfolio": {
                "cash": 10000.0,
                "holdings": [
                    {"code": "000725", "name": "京东方A", "shares": 1400, "cost": 4.5},
                    {"code": "600584", "name": "长电科技", "shares": 800, "cost": 35.0},
                    {"code": "002273", "name": "水晶光电", "shares": 200, "cost": 33.0},
                ],
            },
        }
        close = {
            "portfolio": {
                "cash": 50000.0,
                "holdings": [
                    {"code": "002273", "name": "水晶光电", "shares": 100, "cost": 33.0, "price": 34.0},
                ],
            },
        }
        summary = {
            "as_of": "2026-08-19",
            "realized_pnl": 2021.0,
            "realized_sells": [
                {
                    "code": "000725",
                    "name": "京东方A",
                    "shares": 1400,
                    "realized_pnl": 800.0,
                },
                {
                    "code": "600584",
                    "name": "长电科技",
                    "shares": 800,
                    "realized_pnl": 900.0,
                },
                {
                    "code": "002273",
                    "name": "水晶光电",
                    "shares": 100,
                    "realized_pnl": 321.0,
                },
            ],
            "trades": [
                {
                    "at": "2026-08-19T10:00:00+08:00",
                    "actions": [
                        {"side": "sell", "code": "000725", "name": "京东方A", "shares": 1400, "price": 4.2},
                        {"side": "sell", "code": "600584", "name": "长电科技", "shares": 800, "price": 36.0},
                        {"side": "sell", "code": "002273", "name": "水晶光电", "shares": 100, "price": 34.0},
                    ],
                }
            ],
        }

        with patch(
            "agent_reach.daily_run.quote_fetch.fetch_quotes_map",
            return_value=QuoteFetchResult(),
        ):
            result = build_sell_rules_whatif(
                summary=summary,
                baseline=morning,
                current=close,
                settings=_settings_partial_sell(),
            )

        by_code = {r["code"]: r for r in result.rows}
        assert by_code["000725"]["actual_sold"] == 1400
        assert by_code["000725"]["hypothetical_sold"] == 700
        assert by_code["600584"]["hypothetical_sold"] == 400
        assert by_code["002273"]["actual_sold"] == 100
        assert by_code["002273"]["hypothetical_sold"] == 100
        assert result.hypothetical_realized_pnl == pytest.approx(1171.0, abs=1)
        assert result.realized_pnl_delta == pytest.approx(-850.0, abs=1)

        md = render_sell_rules_whatif_markdown(result)
        assert "## 🔀 卖出规则对比" in md
        assert "京东方A" in md
        assert "700" in md
        assert "1400" in md

    def test_deep_loss_blocked_on_star_board(self):
        """688 STAR board: 35% of 100 shares rounds to 0 lots."""
        morning = {
            "portfolio": {
                "cash": 50000.0,
                "holdings": [
                    {
                        "code": "688008",
                        "name": "澜起科技",
                        "shares": 100,
                        "cost": 260.0,
                        "price": 240.0,
                    },
                ],
            },
        }
        close = {
            "portfolio": {
                "cash": 50000.0,
                "holdings": [
                    {
                        "code": "688008",
                        "name": "澜起科技",
                        "shares": 100,
                        "cost": 260.0,
                        "price": 240.0,
                    },
                ],
            },
        }
        summary = {
            "as_of": "2026-08-19",
            "realized_pnl": 0.0,
            "realized_sells": [],
            "trades": [],
        }
        settings = _settings_partial_sell()
        settings["harness_runtime"]["deep_loss_policy"]["loss_cny_threshold"] = 1000
        settings["harness_runtime"]["deep_loss_policy"]["cover_ratio"] = 0.0

        result = build_sell_rules_whatif(
            summary=summary,
            baseline=morning,
            current=close,
            settings=settings,
        )
        assert len(result.rows) == 1
        row = result.rows[0]
        assert row["code"] == "688008"
        assert row["actual_sold"] == 0
        assert row["hypothetical_sold"] == 0
        assert row["is_deep_loss"] is True
        assert "不足一手" in str(row.get("block_reason") or "")

    def test_skipped_without_morning_holdings(self):
        result = build_sell_rules_whatif(
            summary={"as_of": "2026-08-19", "trades": []},
            baseline={"portfolio": {"holdings": []}},
            current={"portfolio": {"holdings": []}},
            settings=_settings_partial_sell(),
        )
        assert result.skipped is True
        md = render_sell_rules_whatif_markdown(result)
        assert "跳过" in md

    def test_render_in_close_portfolio(self):
        from agent_reach.daily_run.close_portfolio_summary import render_close_portfolio_markdown

        md = render_close_portfolio_markdown(
            {"as_of": "2026-08-19", "holdings": [], "trades": [], "watchlist": []},
            sell_rules_whatif={
                "skipped": False,
                "policy_note": "test",
                "rows": [
                    {
                        "code": "000725",
                        "name": "京东方A",
                        "morning_shares": 1400,
                        "actual_sold": 1400,
                        "hypothetical_sold": 700,
                        "share_delta": -700,
                        "is_deep_loss": False,
                        "sell_ratio": 0.5,
                    }
                ],
                "actual_realized_pnl": 800.0,
                "hypothetical_realized_pnl": 400.0,
                "realized_pnl_delta": -400.0,
            },
        )
        assert "## 🔀 卖出规则对比" in md
        assert "京东方A" in md

    def test_render_intraday_friction_in_close_portfolio(self):
        from agent_reach.daily_run.close_portfolio_summary import render_close_portfolio_markdown

        md = render_close_portfolio_markdown(
            {"as_of": "2026-08-19", "holdings": [], "trades": [], "watchlist": []},
            intraday_friction_whatif={
                "skipped": False,
                "policy_note": "friction **0.005**",
                "friction_blocked_actual": 2,
                "friction_would_pass": 1,
                "trend_mismatch": 0,
                "rows": [
                    {
                        "code": "000725",
                        "name": "京东方A",
                        "actual_action": "hold",
                        "evolved_action": "buy",
                        "actual_friction_blocked": True,
                        "evolved_friction_blocked": False,
                        "block_reason": "MSS 达标",
                    }
                ],
            },
        )
        assert "## 🔀 盘中摩擦/趋势对比" in md
        assert "京东方A" in md
        assert "摩擦阻断 **2**" in md


class TestWeeklySellRulesWhatIf:
    def test_weekly_aggregate_partial_sells(self):
        week_start = date(2026, 8, 18)
        week_end = date(2026, 8, 22)
        morning_snap = {
            "portfolio": {
                "cash": 10000.0,
                "holdings": [
                    {"code": "000725", "name": "京东方A", "shares": 1400, "cost": 4.5},
                    {"code": "002273", "name": "水晶光电", "shares": 200, "cost": 33.0},
                ],
            },
        }
        close_snap = {
            "portfolio": {
                "cash": 50000.0,
                "holdings": [
                    {"code": "002273", "name": "水晶光电", "shares": 100, "cost": 33.0, "price": 34.0},
                ],
            },
        }
        day = "2026-08-19"
        manifests = [
            {
                "_run_date": day,
                "_path": f"/runs/{day}/morning.json",
                "job": "morning",
                "payload": {"result": {"snapshot": morning_snap}},
            },
            {
                "_run_date": day,
                "_path": f"/runs/{day}/close.json",
                "job": "close",
                "payload": {"result": {"snapshot": close_snap}},
            },
        ]
        trades = [
            {
                "at": f"{day}T10:00:00+08:00",
                "actions": [
                    {"side": "sell", "code": "000725", "name": "京东方A", "shares": 1400, "price": 4.2},
                    {"side": "sell", "code": "002273", "name": "水晶光电", "shares": 100, "price": 34.0},
                ],
            }
        ]

        result = build_weekly_sell_rules_whatif(
            week_start=week_start,
            week_end=week_end,
            trades=trades,
            manifests=manifests,
            settings=_settings_partial_sell(),
        )
        assert result.scope == "weekly"
        assert not result.skipped
        by_code = {r["code"]: r for r in result.rows}
        assert by_code["000725"]["actual_sold"] == 1400
        assert by_code["000725"]["hypothetical_sold"] == 700
        assert by_code["002273"]["hypothetical_sold"] == 100

        md = render_sell_rules_whatif_markdown(result)
        assert "统计周期" in md
        assert "基准值卖出" in md
        assert "早盘持仓" not in md

    def test_weekly_skipped_without_trades(self):
        result = build_weekly_sell_rules_whatif(
            week_start=date(2026, 8, 18),
            week_end=date(2026, 8, 22),
            trades=[],
            manifests=[],
            settings=_settings_partial_sell(),
        )
        assert result.skipped is True

    def test_weekly_render_in_report(self):
        from agent_reach.daily_run.weekly_report import WeeklyReport, _render_pnl_lines

        report = WeeklyReport(
            week_start=date(2026, 8, 18),
            week_end=date(2026, 8, 22),
            start_total=100000.0,
            end_total=101000.0,
            weekly_pnl=1000.0,
            weekly_pnl_pct=1.0,
            realized_pnl=800.0,
            sell_rules_whatif={
                "scope": "weekly",
                "skipped": False,
                "policy_note": "test",
                "period_label": "2026-08-18 ~ 2026-08-22",
                "trading_days": 1,
                "rows": [
                    {
                        "code": "000725",
                        "name": "京东方A",
                        "actual_sold": 1400,
                        "hypothetical_sold": 700,
                        "share_delta": -700,
                    }
                ],
                "actual_realized_pnl": 800.0,
                "hypothetical_realized_pnl": 400.0,
                "realized_pnl_delta": -400.0,
            },
        )
        md = "\n".join(_render_pnl_lines(report))
        assert "## 🔀 卖出规则对比" in md
        assert "京东方A" in md

    def test_weekly_intraday_friction_aggregate(self):
        week_start = date(2026, 8, 18)
        week_end = date(2026, 8, 22)
        day = "2026-08-19"
        morning_snap = {
            "portfolio": {
                "cash": 200000.0,
                "holdings": [],
                "watchlist": [{"code": "000725", "name": "京东方A"}],
            },
        }
        close_snap = {
            "portfolio": {
                "cash": 200000.0,
                "holdings": [],
                "watchlist": [{"code": "000725", "name": "京东方A"}],
            },
        }
        manifests = [
            {
                "_run_date": day,
                "_path": f"/runs/{day}/morning.json",
                "job": "morning",
                "payload": {"result": {"snapshot": morning_snap}},
            },
            {
                "_run_date": day,
                "_path": f"/runs/{day}/close.json",
                "job": "close",
                "payload": {
                    "result": {
                        "snapshot": close_snap,
                        "portfolio_summary": {
                            "intraday_trades": [
                                {
                                    "action": "hold",
                                    "lookback_mss": 65,
                                    "trend": "rising",
                                    "verdict": "可做",
                                    "mss_final": 65,
                                    "code": "000725",
                                    "name": "京东方A",
                                    "friction_blocked": True,
                                }
                            ],
                        },
                    }
                },
            },
        ]
        from agent_reach.daily_run.sell_rules_whatif import (
            build_weekly_intraday_friction_whatif,
            render_intraday_friction_whatif_markdown,
        )

        result = build_weekly_intraday_friction_whatif(
            week_start=week_start,
            week_end=week_end,
            manifests=manifests,
            settings={
                "thresholds": {"max_snapshot_age_hours": 24},
                "trading": {"friction_min_return_pct": 0.005, "min_deploy_cash": 1000},
                "intraday": {"trend_min_points": 2, "trend_delta_threshold": 1.0},
                "harness": {"threshold_evolution_mode": "harness"},
            },
        )
        assert result.scope == "weekly"
        assert not result.skipped
        assert result.friction_blocked_actual >= 1
        md = render_intraday_friction_whatif_markdown(result)
        assert "统计周期" in md
        assert "000725" in md or "京东方A" in md

    def test_weekly_render_includes_intraday_friction(self):
        from agent_reach.daily_run.weekly_report import WeeklyReport, _render_pnl_lines

        report = WeeklyReport(
            week_start=date(2026, 8, 18),
            week_end=date(2026, 8, 22),
            start_total=100000.0,
            end_total=101000.0,
            weekly_pnl=1000.0,
            weekly_pnl_pct=1.0,
            realized_pnl=0.0,
            intraday_friction_whatif={
                "scope": "weekly",
                "skipped": False,
                "policy_note": "friction **0.005**",
                "period_label": "2026-08-18 ~ 2026-08-22",
                "trading_days": 2,
                "friction_blocked_actual": 3,
                "friction_would_pass": 1,
                "rows": [
                    {
                        "code": "000725",
                        "name": "京东方A",
                        "actual_action": "hold",
                        "evolved_action": "buy",
                        "actual_friction_blocked": True,
                        "evolved_friction_blocked": False,
                        "block_reason": "MSS 达标",
                    }
                ],
            },
        )
        md = "\n".join(_render_pnl_lines(report))
        assert "## 🔀 盘中摩擦/趋势对比" in md
        assert "京东方A" in md


class TestWhatIfHarnessEvidence:
    def test_baseline_better_evolves_harness_not_revert(self):
        evidence = summarize_whatif_for_harness(
            {
                "skipped": False,
                "scope": "weekly",
                "period_label": "2026-08-18 ~ 2026-08-22",
                "actual_realized_pnl": 2021.0,
                "hypothetical_realized_pnl": 1171.0,
                "realized_pnl_delta": -850.0,
                "rows": [
                    {
                        "code": "000725",
                        "name": "京东方A",
                        "actual_sold": 1400,
                        "hypothetical_sold": 700,
                        "share_delta": -700,
                    }
                ],
            },
            weekly_pnl=500.0,
            weekly_pnl_pct=0.5,
        )
        assert any("基准优于自进化" in line for line in evidence["policy"])
        assert any("条件允许允许全清" in line for line in evidence["policy"])
        assert not any("自进化减仓优于基准" in line for line in evidence["policy"])
        assert any("全清(1.0)" in line for line in evidence["plan"])

    def test_evolved_better_maintains_partial_sell(self):
        evidence = summarize_whatif_for_harness(
            {
                "skipped": False,
                "scope": "weekly",
                "actual_realized_pnl": 500.0,
                "hypothetical_realized_pnl": 900.0,
                "realized_pnl_delta": 400.0,
                "rows": [],
            },
        )
        assert any("自进化优于基准" in line for line in evidence["policy"])

    def test_apply_weekly_harness_refinement(self, harness_tmp):
        from agent_reach.daily_run.sell_rules_whatif_harness import (
            apply_sell_rules_whatif_harness_refinement,
        )

        report = {
            "week_start": "2026-08-18",
            "week_end": "2026-08-22",
            "weekly_pnl": 500.0,
            "weekly_pnl_pct": 0.5,
            "sell_rules_whatif": {
                "skipped": False,
                "scope": "weekly",
                "actual_realized_pnl": 2021.0,
                "hypothetical_realized_pnl": 1171.0,
                "realized_pnl_delta": -850.0,
                "rows": [
                    {
                        "code": "000725",
                        "name": "京东方A",
                        "actual_sold": 1400,
                        "hypothetical_sold": 700,
                        "share_delta": -700,
                    }
                ],
            },
        }
        result = apply_sell_rules_whatif_harness_refinement(
            report,
            settings={
                "harness": {"enabled": True, "jobs": {"sell_rules_whatif": True}},
                "sell_rules_whatif": {"llm_optimize": False},
            },
        )
        assert not result.get("skipped")
        assert result.get("refinement_id")
        assert result.get("llm_optimize", {}).get("skipped") is True


def _settings_buy_evolved():
    return {
        "harness_runtime": {
            "position_policy": {"deploy_ratio": 1.0, "max_position_pct": 2.0},
        },
        "thresholds": {"min_cash_ratio": 0.1, "macro_veto": 40, "aggressive_entry": 50},
        "intraday": {"buy_trends": ["rising", "turning_up", "flat"]},
        "portfolio": {"auto_adjust_enabled": True},
        "trading": {"holding_lock_days": 0, "min_deploy_cash": 1000},
        "pnl_overview": {},
    }


class TestBuyRulesWhatIf:
    def test_partial_deploy_vs_actual_buy(self):
        morning = {
            "portfolio": {
                "cash": 200000.0,
                "total": 200000.0,
                "holdings": [],
                "watchlist": [{"code": "000725", "name": "京东方A"}],
            },
        }
        close = {
            "portfolio": {
                "cash": 194400.0,
                "total": 200000.0,
                "holdings": [{"code": "000725", "name": "京东方A", "shares": 1400, "cost": 4.0}],
                "watchlist": [],
            },
        }
        summary = {
            "as_of": "2026-08-19",
            "trades": [
                {
                    "at": "2026-08-19T10:30:00+08:00",
                    "actions": [
                        {"side": "buy", "code": "000725", "name": "京东方A", "shares": 1400, "price": 4.0},
                    ],
                }
            ],
            "intraday_trades": [
                {
                    "action": "buy",
                    "lookback_mss": 65,
                    "trend": "rising",
                    "verdict": "可做",
                    "mss_final": 65,
                    "code": "000725",
                    "name": "京东方A",
                    "blocked": False,
                    "friction_blocked": False,
                    "portfolio_applied": True,
                    "portfolio_actions": [
                        {"side": "buy", "code": "000725", "name": "京东方A", "shares": 1400, "price": 4.0},
                    ],
                }
            ],
        }

        with patch(
            "agent_reach.daily_run.quote_fetch.fetch_quotes_map",
            return_value=QuoteFetchResult(quotes={"000725": {"price": 4.0, "name": "京东方A"}}),
        ):
            from agent_reach.daily_run.sell_rules_whatif import (
                build_buy_rules_whatif,
                render_buy_rules_whatif_markdown,
                render_trade_rules_whatif_markdown,
            )

            result = build_buy_rules_whatif(
                summary=summary,
                baseline=morning,
                current=close,
                settings=_settings_buy_evolved(),
            )

        assert not result.skipped
        assert len(result.rows) == 1
        row = result.rows[0]
        assert row["actual_bought"] == 1400
        assert row["hypothetical_bought"] == 900
        assert row["share_delta"] == -500

        md = render_buy_rules_whatif_markdown(result)
        assert "## 🔀 买入规则对比" in md
        assert "1400" in md
        assert "1000" in md or "900" in md

        combined = render_trade_rules_whatif_markdown(buy=result)
        assert "买入规则对比" in combined

    def test_skipped_without_buys(self):
        from agent_reach.daily_run.sell_rules_whatif import build_buy_rules_whatif

        result = build_buy_rules_whatif(
            summary={"as_of": "2026-08-19", "trades": [], "intraday_trades": []},
            baseline={"portfolio": {"cash": 10000, "holdings": []}},
            current={"portfolio": {"cash": 10000, "holdings": []}},
            settings=_settings_buy_evolved(),
        )
        assert result.skipped is True


class TestIntradaySellWhatIf:
    def test_missed_macro_veto_sell_signal(self):
        morning = {
            "portfolio": {
                "cash": 50000.0,
                "total": 100000.0,
                "holdings": [
                    {"code": "000725", "name": "京东方A", "shares": 1400, "cost": 4.5},
                ],
            },
        }
        close = {
            "portfolio": {
                "cash": 50000.0,
                "total": 95000.0,
                "holdings": [
                    {"code": "000725", "name": "京东方A", "shares": 1400, "cost": 4.5, "price": 4.0},
                ],
            },
        }
        summary = {
            "as_of": "2026-08-19",
            "intraday_trades": [
                {
                    "action": "hold",
                    "lookback_mss": 28,
                    "trend": "falling",
                    "verdict": "观察",
                    "mss_final": 28,
                    "code": "000725",
                    "name": "京东方A",
                }
            ],
        }
        settings = {
            "thresholds": {"macro_veto": 40, "aggressive_entry": 50, "min_cash_ratio": 0.1},
            "trading": {"holding_lock_days": 0},
            "harness": {"threshold_evolution_mode": "harness"},
        }

        with patch(
            "agent_reach.daily_run.quote_fetch.fetch_quotes_map",
            return_value=QuoteFetchResult(quotes={"000725": {"price": 4.0, "name": "京东方A"}}),
        ):
            from agent_reach.daily_run.sell_rules_whatif import (
                build_intraday_sell_whatif,
                render_intraday_sell_whatif_markdown,
                render_trade_rules_whatif_markdown,
            )

            result = build_intraday_sell_whatif(
                summary=summary,
                baseline=morning,
                current=close,
                settings=settings,
            )

        assert not result.skipped
        assert len(result.rows) == 1
        assert result.missed_sell_signals == 1
        assert result.rows[0]["evolved_action"] == "sell"
        assert result.rows[0]["actual_sold"] == 0
        assert result.rows[0]["hypothetical_sold"] > 0

        md = render_intraday_sell_whatif_markdown(result)
        assert "## 🔀 盘中卖出 scan replay" in md
        assert "京东方A" in md
        assert "错失信号 **1**" in md

        combined = render_trade_rules_whatif_markdown(intraday_sell=result)
        assert "scan replay" in combined

    def test_render_intraday_sell_in_close_portfolio(self):
        from agent_reach.daily_run.close_portfolio_summary import render_close_portfolio_markdown

        md = render_close_portfolio_markdown(
            {"as_of": "2026-08-19", "holdings": [], "trades": [], "watchlist": []},
            intraday_sell_whatif={
                "skipped": False,
                "policy_note": "macro_veto **40**",
                "actual_sell_shares": 0,
                "hypothetical_sell_shares": 700,
                "missed_sell_signals": 1,
                "rows": [
                    {
                        "code": "000725",
                        "name": "京东方A",
                        "actual_action": "hold",
                        "evolved_action": "sell",
                        "actual_sold": 0,
                        "hypothetical_sold": 700,
                        "share_delta": 700,
                        "block_reason": "宏观避险",
                    }
                ],
            },
        )
        assert "## 🔀 盘中卖出 scan replay" in md
        assert "京东方A" in md

    def test_weekly_intraday_sell_aggregate(self):
        week_start = date(2026, 8, 18)
        week_end = date(2026, 8, 22)
        day = "2026-08-19"
        morning_snap = {
            "portfolio": {
                "cash": 50000.0,
                "holdings": [
                    {"code": "000725", "name": "京东方A", "shares": 1400, "cost": 4.5},
                ],
            },
        }
        close_snap = {
            "portfolio": {
                "cash": 50000.0,
                "holdings": [
                    {"code": "000725", "name": "京东方A", "shares": 1400, "cost": 4.5, "price": 4.0},
                ],
            },
        }
        manifests = [
            {
                "_run_date": day,
                "_path": f"/runs/{day}/morning.json",
                "job": "morning",
                "payload": {"result": {"snapshot": morning_snap}},
            },
            {
                "_run_date": day,
                "_path": f"/runs/{day}/close.json",
                "job": "close",
                "payload": {
                    "result": {
                        "snapshot": close_snap,
                        "portfolio_summary": {
                            "intraday_trades": [
                                {
                                    "action": "hold",
                                    "lookback_mss": 28,
                                    "trend": "falling",
                                    "verdict": "观察",
                                    "mss_final": 28,
                                    "code": "000725",
                                    "name": "京东方A",
                                }
                            ],
                        },
                    }
                },
            },
        ]

        with patch(
            "agent_reach.daily_run.quote_fetch.fetch_quotes_map",
            return_value=QuoteFetchResult(quotes={"000725": {"price": 4.0, "name": "京东方A"}}),
        ):
            from agent_reach.daily_run.sell_rules_whatif import (
                build_weekly_intraday_sell_whatif,
                render_intraday_sell_whatif_markdown,
            )

            result = build_weekly_intraday_sell_whatif(
                week_start=week_start,
                week_end=week_end,
                manifests=manifests,
                settings={
                    "thresholds": {"macro_veto": 40, "aggressive_entry": 50, "min_cash_ratio": 0.1},
                    "trading": {"holding_lock_days": 0},
                    "harness": {"threshold_evolution_mode": "harness"},
                },
            )

        assert result.scope == "weekly"
        assert not result.skipped
        assert result.missed_sell_signals >= 1
        md = render_intraday_sell_whatif_markdown(result)
        assert "统计周期" in md
        assert "000725" in md or "京东方A" in md

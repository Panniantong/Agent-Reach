# -*- coding: utf-8
"""Tests for weekly report generation and schedule integration."""

import json
from datetime import date
from unittest.mock import patch

import pytest

from agent_reach.daily_run.weekly_report import (
    _compute_realized_pnl,
    _compute_trade_cash_flow,
    build_mss_trajectory,
    generate_weekly_report,
    render_weekly_markdown,
    trading_week_range,
    weekly_report_title,
)


@pytest.fixture
def portfolio():
    return {
        "total": 100000,
        "cash": 40000,
        "cash_ratio": 0.4,
        "holdings": [
            {"code": "688008", "name": "澜起科技", "shares": 100, "cost": 250.0},
            {"code": "002273", "name": "水晶光电", "shares": 300, "cost": 30.0},
        ],
        "watchlist": [
            {"code": "603986", "name": "兆易创新"},
        ],
    }


@pytest.fixture
def snapshot(portfolio):
    return {
        "code": "688008",
        "name": "澜起科技",
        "price": 260.0,
        "change_pct": 2.5,
        "portfolio": portfolio,
        "watchlist": portfolio["watchlist"],
        "holdings": portfolio["holdings"],
    }


class TestTradingWeekRange:
    def test_saturday_returns_previous_week(self):
        sat = date(2026, 7, 11)  # Saturday
        mon, fri = trading_week_range(sat)
        assert mon == date(2026, 7, 6)
        assert fri == date(2026, 7, 10)

    def test_friday_same_week(self):
        fri = date(2026, 7, 10)
        mon, end = trading_week_range(fri)
        assert mon == date(2026, 7, 6)
        assert end == date(2026, 7, 10)


class TestMssTrajectory:
    def test_build_mss_trajectory_one_point_per_day(self):
        manifests = []
        for day, morning, close in [
            ("2026-07-08", 48.0, 49.1),
            ("2026-07-09", 50.0, 51.2),
            ("2026-07-10", 48.0, 48.9),
        ]:
            manifests.append(
                {
                    "_run_date": day,
                    "_path": f"/runs/{day}/morning_080000.json",
                    "job": "morning",
                    "payload": {
                        "result": {
                            "snapshot": {"mss_final": morning},
                            "evaluation": {"report": {"mss_final": morning}},
                        }
                    },
                }
            )
            for i in range(5):
                manifests.append(
                    {
                        "_run_date": day,
                        "_path": f"/runs/{day}/morning_{i:06d}.json",
                        "job": "morning",
                        "payload": {
                            "result": {
                                "snapshot": {"mss_final": morning + i},
                                "evaluation": {"report": {"mss_final": morning + i}},
                            }
                        },
                    }
                )
            manifests.append(
                {
                    "_run_date": day,
                    "_path": f"/runs/{day}/close_153000.json",
                    "job": "close",
                    "payload": {
                        "result": {
                            "verify": {"mss_current": close},
                            "snapshot": {"mss_final": close},
                        }
                    },
                }
            )

        traj = build_mss_trajectory(manifests, date(2026, 7, 6), date(2026, 7, 10))
        dates = sorted({r["date"] for r in traj})
        assert dates == ["2026-07-08", "2026-07-09", "2026-07-10"]
        assert len(traj) == 6  # morning + close per day

    @patch("agent_reach.daily_run.weekly_report._load_week_manifests")
    @patch("agent_reach.daily_run.weekly_report._load_trade_ledger_range", return_value=[])
    @patch("agent_reach.daily_run.weekly_report.run_sector_research", return_value=[])
    def test_weekly_markdown_shows_all_days(self, mock_exa, mock_ledger, mock_manifests, snapshot, portfolio):
        mock_manifests.return_value = [
            {
                "_run_date": "2026-07-08",
                "_path": "/r/2026-07-08/morning.json",
                "job": "morning",
                "payload": {"result": {"snapshot": {"mss_final": 48.0}}},
            },
            {
                "_run_date": "2026-07-08",
                "_path": "/r/2026-07-08/close.json",
                "job": "close",
                "payload": {"result": {"verify": {"mss_current": 49.1}}},
            },
            {
                "_run_date": "2026-07-10",
                "_path": "/r/2026-07-10/morning.json",
                "job": "morning",
                "payload": {"result": {"snapshot": {"mss_final": 50.0}}},
            },
            {
                "_run_date": "2026-07-10",
                "_path": "/r/2026-07-10/close.json",
                "job": "close",
                "payload": {"result": {"verify": {"mss_current": 48.9}}},
            },
        ]
        report = generate_weekly_report(
            snapshot,
            {
                "weekly_report": {
                    "exa_sector_research": False,
                    "skill_learning": False,
                    "process_improvements": False,
                }
            },
            as_of=date(2026, 7, 11),
            portfolio=portfolio,
        )
        md = render_weekly_markdown(report)
        assert "07-08" in md
        assert "07-10" in md
        assert md.count("07-10") >= 1
        assert "07-08" in md


class TestWeeklyReport:
    def test_compute_trade_cash_flow(self):
        trades = [
            {
                "actions": [
                    {"side": "buy", "amount": 10000, "commission": 15},
                    {"side": "sell", "amount": 10500, "commission": 16},
                ]
            }
        ]
        assert _compute_trade_cash_flow(trades) == 469.0

    def test_compute_realized_pnl(self):
        trades = [
            {
                "actions": [
                    {"side": "buy", "amount": 10000, "commission": 15},
                    {"side": "sell", "amount": 10500, "commission": 16},
                ]
            }
        ]
        assert _compute_realized_pnl(trades) == 469.0

    def test_compute_realized_pnl_buy_only_is_zero(self):
        trades = [
            {
                "actions": [
                    {
                        "side": "buy",
                        "code": "000725",
                        "shares": 5300,
                        "amount": 39750.0,
                        "commission": 59.62,
                    }
                ]
            }
        ]
        assert _compute_realized_pnl(trades) == 0.0
        assert _compute_trade_cash_flow(trades) == -39809.62

    @patch("agent_reach.daily_run.weekly_report.run_sector_research", return_value=[])
    @patch("agent_reach.daily_run.weekly_report._load_week_manifests", return_value=[])
    @patch("agent_reach.daily_run.weekly_report._load_trade_ledger_range", return_value=[])
    @patch(
        "agent_reach.daily_run.watchlist_intel.collect_watchlist_intel",
        return_value={
            "603986": {
                "name": "兆易创新",
                "announcements": [{"title": "业绩预告"}],
            }
        },
    )
    def test_generate_weekly_report(self, mock_intel, mock_ledger, mock_manifests, mock_exa, snapshot, portfolio):
        report = generate_weekly_report(
            snapshot,
            {"weekly_report": {"enabled": True, "exa_sector_research": False}},
            as_of=date(2026, 7, 11),
            portfolio=portfolio,
        )
        assert report.week_start == date(2026, 7, 6)
        assert report.end_total == 75000
        assert len(report.holdings) == 2
        assert len(report.watchlist) == 1
        assert report.watchlist_intel["603986"]["name"] == "兆易创新"
        assert report.to_dict()["watchlist_intel"]["603986"]["name"] == "兆易创新"
        assert "澜起科技" in render_weekly_markdown(report)
        assert "股市技能学习" in render_weekly_markdown(report)
        assert "流程改进意见" in render_weekly_markdown(report)

    @patch("agent_reach.daily_run.weekly_report.run_sector_research", return_value=[])
    @patch("agent_reach.daily_run.weekly_report._load_week_manifests", return_value=[])
    @patch("agent_reach.daily_run.weekly_report._load_trade_ledger_range", return_value=[])
    @patch("agent_reach.daily_run.weekly_report._portfolio_from_morning_baseline")
    def test_generate_weekly_report_fallback_when_portfolio_empty(
        self,
        mock_baseline,
        mock_ledger,
        mock_manifests,
        mock_exa,
        portfolio,
    ):
        mock_baseline.return_value = portfolio
        empty_snapshot = {"code": "688008", "portfolio": {"holdings": []}, "watchlist": []}
        report = generate_weekly_report(
            empty_snapshot,
            {"weekly_report": {"enabled": True, "exa_sector_research": False}},
            as_of=date(2026, 7, 11),
            portfolio={"holdings": []},
        )
        assert len(report.holdings) == 2
        assert len(report.watchlist) == 1
        assert any("last_morning.json" in n for n in report.notes)

    def test_weekly_report_title(self):
        from agent_reach.daily_run.weekly_report import WeeklyReport

        report = WeeklyReport(
            week_start=date(2026, 7, 6),
            week_end=date(2026, 7, 10),
            start_total=98000,
            end_total=100000,
            weekly_pnl=2000,
            weekly_pnl_pct=2.04,
            realized_pnl=0,
        )
        title = weekly_report_title(report)
        assert "周报" in title
        assert "+¥2,000" in title

    def test_build_weekly_pnl_attribution(self):
        from agent_reach.daily_run.weekly_report import (
            WeeklyReport,
            build_weekly_pnl_attribution_lines,
        )

        report = WeeklyReport(
            week_start=date(2026, 7, 27),
            week_end=date(2026, 7, 31),
            start_total=84402.27,
            end_total=84197.27,
            weekly_pnl=-205.0,
            weekly_pnl_pct=-0.24,
            realized_pnl=0.0,
            trade_cash_flow=-199048.1,
            start_cash=44000.0,
            end_cash=40176.27,
            start_stock_mv=40402.27,
            end_stock_mv=44021.0,
            stock_pnl=3618.73,
            cash_pnl=-3823.73,
        )
        text = "\n".join(build_weekly_pnl_attribution_lines(report))
        assert "盈亏分解" in text
        assert "股票市值" in text
        assert "持有现金" in text
        assert "44,402.27" in text or "44,021" in text

    def test_compute_weekly_stock_cash_pnl_uses_balance_not_trade_flow(self):
        from agent_reach.daily_run.weekly_report import _compute_weekly_stock_cash_pnl

        cash_pnl, stock_pnl, notes = _compute_weekly_stock_cash_pnl(
            weekly_pnl=-103896.59,
            start_cash=140176.27,
            end_cash=28472.68,
            start_stock_mv=45901.0,
            end_stock_mv=53708.0,
            holdings_changed=True,
            trades=[{"actions": [{"side": "sell"}]}],
            manifest_cash_pnl=-111703.59,
        )
        assert cash_pnl == -111703.59
        assert stock_pnl == 7807.0
        assert round(cash_pnl + stock_pnl, 2) == -103896.59
        assert not any("ledger 成交重算" in n for n in notes)

    def test_build_weekly_pnl_attribution_rebalance(self):
        from agent_reach.daily_run.weekly_report import (
            build_weekly_pnl_attribution,
            build_weekly_pnl_source_attribution_lines,
        )

        attr = build_weekly_pnl_attribution(
            weekly_pnl=-103896.59,
            cash_pnl=-111703.59,
            stock_pnl=7807.0,
            realized_pnl=3419.66,
            trade_cash_flow=20784.9,
            holdings=[
                {"week_chg": -1136.0},
                {"week_chg": -425.0},
                {"week_chg": -28.0},
                {"week_chg": -14.0},
            ],
        )
        assert attr["held_week_chg"] == -1603.0
        assert attr["realized_pnl"] == 3419.66
        assert attr["rebalance_pnl"] == -105713.25

        lines = build_weekly_pnl_source_attribution_lines(
            {"weekly_pnl": -103896.59, "pnl_attribution": attr, "cash_pnl": -111703.59}
        )
        text = "\n".join(lines)
        assert "归因明细" in text
        assert "现持仓价格" in text
        assert "已清仓已实现" in text
        assert "换仓及其它" in text
        assert "成交净现金流" in text

    def test_render_pnl_lines_includes_trade_pnl_detail(self):
        from agent_reach.daily_run.weekly_report import WeeklyReport, _render_pnl_lines

        report = WeeklyReport(
            week_start=date(2026, 8, 17),
            week_end=date(2026, 8, 21),
            start_total=186077.27,
            end_total=82180.68,
            weekly_pnl=-103896.59,
            weekly_pnl_pct=-55.84,
            realized_pnl=3419.66,
            trade_cash_flow=20784.9,
            trade_pnl_detail={
                "realized_pnl": 3419.66,
                "sells": [
                    {
                        "name": "京东方A",
                        "code": "000725",
                        "shares": 1400,
                        "price": 6.47,
                        "avg_buy_price": 6.58,
                        "realized_pnl": -1471.34,
                        "realized_pnl_pct": -13.99,
                        "at": "2026-08-19T02:00:00+00:00",
                        "date": "2026-08-19",
                    }
                ],
                "buys": [
                    {
                        "side": "buy",
                        "name": "海能达",
                        "code": "002583",
                        "shares": 1500,
                        "price": 8.11,
                        "amount": 12165.0,
                        "commission": 18.25,
                        "at": "2026-08-21T03:00:00+00:00",
                        "date": "2026-08-21",
                        "status": "held",
                        "week_end_price": 8.12,
                        "floating_pnl": 15.0,
                        "floating_pnl_pct": 0.12,
                    }
                ],
            },
        )
        text = "\n".join(_render_pnl_lines(report))
        assert "股票盈亏明细" in text
        assert "本周交易" in text
        assert "京东方A" in text
        assert "海能达" in text
        assert "已实现" in text
        assert "浮盈浮亏" in text

    def test_load_trade_ledger_range_dedupes(self, tmp_path, monkeypatch):
        from agent_reach.daily_run.weekly_report import _load_trade_ledger_range

        ledger = tmp_path / "trade_ledger.jsonl"
        dup = {
            "at": "2026-07-29T13:44:18+00:00",
            "actions": [
                {
                    "side": "buy",
                    "code": "000725",
                    "shares": 5300,
                    "price": 7.5,
                    "amount": 39750.0,
                    "commission": 59.62,
                }
            ],
        }
        ledger.write_text("\n".join(json.dumps(dup, ensure_ascii=False) for _ in range(3)) + "\n", encoding="utf-8")
        monkeypatch.setattr("agent_reach.daily_run.weekly_report.default_ledger_path", lambda: ledger)

        rows = _load_trade_ledger_range(date(2026, 7, 27), date(2026, 7, 31))
        assert len(rows) == 1

    def test_build_weekly_pnl_explanation(self):
        from agent_reach.daily_run.weekly_report import (
            WeeklyReport,
            _render_pnl_lines,
            build_weekly_pnl_explanation,
        )

        report = WeeklyReport(
            week_start=date(2026, 7, 20),
            week_end=date(2026, 7, 24),
            start_total=87323.27,
            end_total=87323.27,
            weekly_pnl=0.0,
            weekly_pnl_pct=0.0,
            realized_pnl=0.0,
            trade_cash_flow=-48306.35,
            cash=40176.27,
            cash_ratio=0.4601,
            holdings=[
                {
                    "name": "京东方A",
                    "code": "000725",
                    "unrealized_pnl": -378,
                    "week_chg": -420,
                },
                {
                    "name": "澜起科技",
                    "code": "688008",
                    "unrealized_pnl": -2221,
                    "week_chg": 850,
                },
            ],
            trades=[{"at": "2026-07-24", "actions": [{"side": "buy", "name": "京东方A", "shares": 1400, "price": 6.06}]}],
            notes=["缺少周初净值基线，无法计算周度组合盈亏"],
            daily_totals=[
                {"date": "2026-07-23", "total": 87000, "job": "close"},
                {"date": "2026-07-24", "total": 87323.27, "job": "close"},
            ],
        )
        expl = build_weekly_pnl_explanation(report)
        text = "\n".join(expl)
        assert "情况说明" in text
        assert "持平" in text
        assert "持仓浮盈合计" in text
        assert "现金仓位" in text
        assert "成交现金流" in text
        assert "京东方A" in text

        rendered = "\n".join(_render_pnl_lines(report))
        assert "情况说明" in rendered
        assert "缺少周初净值基线" in rendered

    @patch("agent_reach.daily_run.weekly_report._load_manifest")
    @patch("agent_reach.daily_run.weekly_report.runs_dir")
    def test_manifest_pnl_from_symbol_runner_morning(self, mock_runs_dir, mock_load, tmp_path, snapshot, portfolio):
        day_dir = tmp_path / "2026-07-06"
        day_dir.mkdir()
        end_dir = tmp_path / "2026-07-10"
        end_dir.mkdir()
        mock_runs_dir.return_value = tmp_path

        morning_manifest = {
            "job": "morning",
            "payload": {
                "symbol_results": [
                    {
                        "code": "688008",
                        "result": {
                            "snapshot": {
                                "code": "688008",
                                "price": 250.0,
                                "portfolio": {"total": 98000, "cash": 40000, "holdings": portfolio["holdings"]},
                            }
                        },
                    },
                    {
                        "code": "002273",
                        "result": {
                            "snapshot": {
                                "code": "002273",
                                "price": 30.0,
                                "portfolio": {"total": 98000, "cash": 40000, "holdings": portfolio["holdings"]},
                            }
                        },
                    },
                ]
            },
        }
        close_manifest = {
            "job": "close",
            "payload": {
                "symbol_results": [
                    {
                        "code": "688008",
                        "result": {
                            "snapshot": {
                                "code": "688008",
                                "price": 260.0,
                                "portfolio": {"total": 100500, "cash": 40000, "holdings": portfolio["holdings"]},
                            }
                        },
                    },
                    {
                        "code": "002273",
                        "result": {
                            "snapshot": {
                                "code": "002273",
                                "price": 30.0,
                                "portfolio": {"total": 100500, "cash": 40000, "holdings": portfolio["holdings"]},
                            }
                        },
                    },
                ]
            },
        }

        def _load_side_effect(path):
            if "morning" in path.name:
                return morning_manifest
            if "close" in path.name:
                return close_manifest
            return None

        (day_dir / "morning_080000.json").write_text("{}", encoding="utf-8")
        (end_dir / "close_153000.json").write_text("{}", encoding="utf-8")
        mock_load.side_effect = _load_side_effect

        with patch("agent_reach.daily_run.weekly_report.run_sector_research", return_value=[]):
            with patch("agent_reach.daily_run.weekly_report._load_trade_ledger_range", return_value=[]):
                report = generate_weekly_report(
                    snapshot,
                    {"weekly_report": {"exa_sector_research": False}},
                    as_of=date(2026, 7, 11),
                    portfolio=portfolio,
                )

        assert report.start_total == 74000
        assert report.end_total == 75000
        assert report.weekly_pnl == 1000

    @patch("agent_reach.daily_run.weekly_report._load_manifest")
    @patch("agent_reach.daily_run.weekly_report.runs_dir")
    def test_manifest_pnl_from_close_runs(self, mock_runs_dir, mock_load, tmp_path, snapshot, portfolio):
        day_dir = tmp_path / "2026-07-10"
        day_dir.mkdir()
        morning_dir = tmp_path / "2026-07-06"
        morning_dir.mkdir()
        mock_runs_dir.return_value = tmp_path

        morning_manifest = {
            "job": "morning",
            "payload": {
                "result": {
                    "snapshot": {"portfolio": {"total": 98000}},
                }
            },
        }
        close_manifest = {
            "job": "close",
            "payload": {
                "result": {
                    "snapshot": {"portfolio": {"total": 100500}, "mss_final": 48},
                }
            },
        }

        def _load_side_effect(path):
            name = path.name
            if "morning" in name:
                return morning_manifest
            if "close" in name:
                return close_manifest
            return None

        (morning_dir / "morning_080000.json").write_text("{}", encoding="utf-8")
        (day_dir / "close_153000.json").write_text("{}", encoding="utf-8")
        mock_load.side_effect = _load_side_effect

        with patch("agent_reach.daily_run.weekly_report.run_sector_research", return_value=[]):
            with patch("agent_reach.daily_run.weekly_report._load_trade_ledger_range", return_value=[]):
                report = generate_weekly_report(
                    snapshot,
                    {"weekly_report": {"exa_sector_research": False}},
                    as_of=date(2026, 7, 11),
                    portfolio=portfolio,
                )

        assert report.start_total == 98000
        assert report.end_total == 100500
        assert report.weekly_pnl == 2500

    @patch("agent_reach.daily_run.weekly_report.run_sector_research", return_value=[])
    @patch("agent_reach.daily_run.weekly_report._load_trade_ledger_range", return_value=[])
    def test_week_start_prices_from_morning_manifest(
        self, mock_ledger, mock_exa, snapshot, portfolio, tmp_path, monkeypatch
    ):
        from agent_reach.daily_run.weekly_report import (
            _week_start_prices_from_manifests,
            generate_weekly_report,
        )

        monkeypatch.setattr(
            "agent_reach.daily_run.weekly_report.runs_dir",
            lambda: tmp_path,
        )
        day_dir = tmp_path / "2026-07-06"
        day_dir.mkdir()
        morning_manifest = {
            "job": "morning",
            "payload": {
                "result": {
                    "snapshot": {
                        "code": "688008",
                        "price": 250.0,
                        "portfolio": portfolio,
                        "holdings": portfolio["holdings"],
                        "watchlist": portfolio["watchlist"],
                    }
                }
            },
        }
        (day_dir / "morning_080000.json").write_text("{}", encoding="utf-8")

        with patch(
            "agent_reach.daily_run.weekly_report._load_manifest",
            return_value=morning_manifest,
        ):
            prices, note = _week_start_prices_from_manifests(
                [{"job": "morning", "_run_date": "2026-07-06", **morning_manifest}],
                date(2026, 7, 6),
            )
        assert prices.get("688008") == 250.0
        assert note is None

        with patch("agent_reach.daily_run.weekly_report._load_week_manifests") as mock_m:
            mock_m.return_value = [
                {"job": "morning", "_run_date": "2026-07-06", **morning_manifest}
            ]
            with patch(
                "agent_reach.daily_run.weekly_report._load_manifest",
                return_value=morning_manifest,
            ):
                report = generate_weekly_report(
                    snapshot,
                    {"weekly_report": {"exa_sector_research": False}},
                    as_of=date(2026, 7, 11),
                    portfolio=portfolio,
                )
        holding = report.holdings[0]
        assert holding.get("week_chg_pct") is not None
        assert "本周盈亏" in render_weekly_markdown(report)

    def test_week_start_prices_fallback_prior_close(self, tmp_path, monkeypatch, portfolio):
        from agent_reach.daily_run.weekly_report import _week_start_prices_from_manifests

        monkeypatch.setattr("agent_reach.daily_run.weekly_report.runs_dir", lambda: tmp_path)
        fri_dir = tmp_path / "2026-07-31"
        fri_dir.mkdir()
        close_manifest = {
            "job": "close",
            "payload": {
                "symbol_results": [
                    {
                        "code": "688008",
                        "result": {
                            "snapshot": {
                                "code": "688008",
                                "price": 200.0,
                                "portfolio": portfolio,
                            }
                        },
                    },
                    {
                        "code": "002273",
                        "result": {
                            "snapshot": {
                                "code": "002273",
                                "price": 25.0,
                                "portfolio": portfolio,
                            }
                        },
                    },
                ]
            },
        }
        (fri_dir / "close_153000.json").write_text("{}", encoding="utf-8")
        with patch(
            "agent_reach.daily_run.weekly_report._load_manifest",
            return_value=close_manifest,
        ):
            prices, note = _week_start_prices_from_manifests([], date(2026, 8, 3))
        assert prices.get("688008") == 200.0
        assert note is not None
        assert "2026-07-31" in note

    def test_week_end_prices_from_last_close_manifest(self, tmp_path, monkeypatch, portfolio):
        from agent_reach.daily_run.weekly_report import _week_end_prices_from_manifests

        close_manifest = {
            "job": "close",
            "payload": {
                "symbol_results": [
                    {
                        "code": "688008",
                        "result": {
                            "snapshot": {
                                "code": "688008",
                                "price": 88.5,
                                "portfolio": portfolio,
                            }
                        },
                    },
                ]
            },
        }
        manifests = [
            {"job": "close", "_run_date": "2026-08-05", **close_manifest},
            {
                "job": "close",
                "_run_date": "2026-08-07",
                "payload": {
                    "symbol_results": [
                        {
                            "code": "688008",
                            "result": {
                                "snapshot": {
                                    "code": "688008",
                                    "price": 92.0,
                                    "portfolio": portfolio,
                                }
                            },
                        },
                    ]
                },
            },
        ]
        prices, note = _week_end_prices_from_manifests(manifests, date(2026, 8, 7))
        assert prices.get("688008") == 92.0
        assert note is None

    @patch("agent_reach.daily_run.weekly_report.run_sector_research", return_value=[])
    @patch("agent_reach.daily_run.weekly_report._load_trade_ledger_range", return_value=[])
    def test_holdings_show_weekend_close_price(
        self, mock_ledger, mock_exa, snapshot, portfolio, tmp_path, monkeypatch
    ):
        from agent_reach.daily_run.weekly_report import generate_weekly_report, render_weekly_markdown

        monkeypatch.setattr("agent_reach.daily_run.weekly_report.runs_dir", lambda: tmp_path)
        week_morning = {
            "job": "morning",
            "_run_date": "2026-08-04",
            "payload": {
                "result": {
                    "snapshot": {
                        "code": "688008",
                        "price": 80.0,
                        "portfolio": portfolio,
                        "holdings": portfolio["holdings"],
                    }
                }
            },
        }
        week_close = {
            "job": "close",
            "_run_date": "2026-08-07",
            "payload": {
                "symbol_results": [
                    {
                        "code": "688008",
                        "result": {
                            "snapshot": {
                                "code": "688008",
                                "price": 85.0,
                                "portfolio": portfolio,
                                "holdings": portfolio["holdings"],
                            }
                        },
                    },
                ]
            },
        }

        with patch(
            "agent_reach.daily_run.weekly_report._load_week_manifests",
            return_value=[week_morning, week_close],
        ):
            report = generate_weekly_report(
                snapshot,
                {"weekly_report": {"exa_sector_research": False}},
                as_of=date(2026, 8, 8),
                portfolio=portfolio,
            )

        holding = next(h for h in report.holdings if h["code"] == "688008")
        assert holding["week_end_price"] == 85.0
        assert holding["week_start_price"] == 80.0
        md = render_weekly_markdown(report)
        assert "周末收盘 ¥85.00" in md
        assert "周初 ¥80.00" in md
        assert "成本浮盈" in md
        assert holding.get("unrealized_pnl") == -16500.0
        assert "成本浮盈 ¥-16,500" in md


class TestScheduleWeekly:
    @patch("agent_reach.daily_run.workflows.run_weekly")
    @patch("agent_reach.daily_run.snapshot_builder.build_and_save")
    @patch("agent_reach.daily_run.snapshot_builder.load_portfolio")
    def test_run_scheduled_weekly_skips_trading_day_check(
        self, mock_load, mock_build, mock_run_weekly, portfolio, tmp_path, monkeypatch
    ):
        from agent_reach.daily_run.schedule import run_scheduled

        monkeypatch.setattr("agent_reach.daily_run.run_manifest.runs_dir", lambda: tmp_path / "runs")
        mock_load.return_value = portfolio
        mock_build.return_value = ({"code": "688008"}, tmp_path / "snap.json")
        mock_run_weekly.return_value = {
            "steps": ["generate", "render"],
            "report": {"weekly_pnl": 1000},
            "markdown": "weekly",
        }

        with patch("agent_reach.daily_run.trade_calendar.is_trading_day", return_value=(False, "周末")):
            result = run_scheduled("weekly", push=False)

        assert result["job"] == "weekly"
        assert not result.get("skipped")
        mock_run_weekly.assert_called_once()

    @patch("agent_reach.daily_run.workflows.run_weekly")
    @patch("agent_reach.daily_run.snapshot_builder.build_and_save")
    @patch("agent_reach.daily_run.snapshot_builder.load_portfolio")
    def test_run_scheduled_weekly_dedupes_same_day(
        self, mock_load, mock_build, mock_run_weekly, portfolio, tmp_path, monkeypatch
    ):
        from agent_reach.daily_run.run_manifest import save_run_manifest
        from agent_reach.daily_run.schedule import run_scheduled

        monkeypatch.setattr("agent_reach.daily_run.run_manifest.runs_dir", lambda: tmp_path / "runs")
        save_run_manifest(
            "weekly",
            {"job": "weekly", "result": {}},
            feishu={"code": 0},
        )

        mock_load.return_value = portfolio
        result = run_scheduled("weekly", push=False)

        assert result.get("skipped") is True
        mock_run_weekly.assert_not_called()

    def test_default_entries_includes_weekly(self):
        from agent_reach.daily_run.schedule import default_entries

        entries = default_entries()
        assert len(entries) == 18
        assert any("weekly" in e.job for e in entries)
        assert any("forecast" in e.job for e in entries)
        assert any(e.weekday == "6" and e.hour == "8" and e.minute == "30" for e in entries)
        assert any(e.weekday == "0" and e.hour == "8" and e.minute == "30" for e in entries)

    def test_render_crontab_includes_weekly(self):
        from agent_reach.daily_run.schedule import render_crontab_block

        block = render_crontab_block()
        assert "daily-run-local-cron.sh weekly" in block
        assert "30 8 * * 6" in block


class TestWeeklyXueqiuHitSection:
    @patch("agent_reach.daily_run.xueqiu_hit_outcomes.summarize_xueqiu_hit_outcomes")
    def test_render_weekly_sections_includes_hit_rate(self, mock_stats):
        from agent_reach.daily_run.weekly_report import WeeklyReport, render_weekly_sections

        mock_stats.return_value = {
            "total": 8,
            "hits": 5,
            "misses": 3,
            "hit_rate": 0.625,
            "window_days": 30,
            "by_type": {"hot_stock": {"hit": 3, "total": 5}},
        }
        report = WeeklyReport(
            week_start=date(2026, 8, 10),
            week_end=date(2026, 8, 14),
            start_total=100000,
            end_total=99212,
            weekly_pnl=-788,
            weekly_pnl_pct=-0.9,
            realized_pnl=0,
        )
        sections = render_weekly_sections(report)
        labels = [s.label for s in sections]
        assert "雪球命中率" in labels
        hit_section = next(s for s in sections if s.label == "雪球命中率")
        assert "命中率" in hit_section.markdown

    def test_render_weekly_sections_includes_watchlist_intel(self):
        from agent_reach.daily_run.weekly_report import WeeklyReport, render_weekly_sections

        report = WeeklyReport(
            week_start=date(2026, 8, 10),
            week_end=date(2026, 8, 14),
            start_total=100000,
            end_total=99212,
            weekly_pnl=-788,
            weekly_pnl_pct=-0.9,
            realized_pnl=0,
            watchlist=[{"code": "603986", "name": "兆易创新"}],
            watchlist_intel={
                "603986": {
                    "name": "兆易创新",
                    "announcements": [{"title": "业绩预告"}],
                }
            },
        )
        sections = render_weekly_sections(report)
        labels = [s.label for s in sections]
        assert "观察池情报" in labels
        intel_section = next(s for s in sections if s.label == "观察池情报")
        assert "兆易创新" in intel_section.markdown


class TestWeeklyExperienceSnippets:
    def test_dedupes_by_symbol_and_covers_week(self, tmp_path, monkeypatch):
        from agent_reach.daily_run import experience as exp_mod
        from agent_reach.daily_run.experience import load_weekly_experience_snippets

        exp_dir = tmp_path / "experience"
        exp_dir.mkdir()
        monkeypatch.setattr(exp_mod, "experience_dir", lambda: exp_dir)
        path = exp_dir / "experience.jsonl"
        entries = [
            {"date": "2026-08-19", "at": "t1", "code": "688008", "name": "澜起科技", "mss_final": 45, "prediction_hit": True, "rules": ["old"]},
            {"date": "2026-08-19", "at": "t2", "code": "688008", "name": "澜起科技", "mss_final": 46, "prediction_hit": True, "rules": ["dup"]},
            {"date": "2026-08-19", "at": "t3", "code": "002273", "name": "水晶光电", "mss_final": 50, "prediction_hit": False, "rules": ["flow"]},
            {"date": "2026-08-21", "at": "t4", "code": "688008", "name": "澜起科技", "mss_final": 48, "prediction_hit": True, "rules": ["latest"]},
            {"date": "2026-08-21", "at": "t5", "code": "002583", "name": "海能达", "mss_final": 42, "prediction_hit": False, "rules": ["risk"]},
            {"date": "2026-08-22", "at": "t6", "code": "600584", "name": "长电科技", "mss_final": 44, "prediction_hit": True, "rules": ["skip"]},
        ]
        path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n", encoding="utf-8")

        snippets = load_weekly_experience_snippets(date(2026, 8, 17), date(2026, 8, 21), limit=5)
        names = [s.split()[1] for s in snippets]
        assert names.count("澜起科技") == 1
        assert "水晶光电" in names
        assert "海能达" in names
        assert "长电科技" not in names
        assert any("MSS=48" in s and "澜起科技" in s for s in snippets)

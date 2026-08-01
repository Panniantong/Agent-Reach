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
    def test_generate_weekly_report(self, mock_ledger, mock_manifests, mock_exa, snapshot, portfolio):
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
            prices = _week_start_prices_from_manifests(
                [{"job": "morning", "_run_date": "2026-07-06", **morning_manifest}],
                date(2026, 7, 6),
            )
        assert prices.get("688008") == 250.0

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
        assert any(e.weekday == "6" and e.hour == "9" for e in entries)
        assert any(e.weekday == "0" and e.hour == "9" for e in entries)

    def test_render_crontab_includes_weekly(self):
        from agent_reach.daily_run.schedule import render_crontab_block

        block = render_crontab_block()
        assert "daily-run-local-cron.sh weekly" in block
        assert "0 9 * * 6" in block

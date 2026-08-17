# -*- coding: utf-8
"""Cron chain smoke: morning → intraday → close → weekly with harness manifest."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from agent_reach.daily_run.intraday import IntradayState


@pytest.fixture
def portfolio():
    return {
        "primary_code": "688008",
        "total": 100000,
        "cash_ratio": 0.5,
        "holdings": [{"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.0}],
        "watchlist": [],
    }


class TestScheduleHarnessSmoke:
    @patch("agent_reach.daily_run.trade_calendar.is_trading_day", return_value=(True, ""))
    @patch("agent_reach.daily_run.schedule._uses_per_symbol_jobs", return_value=False)
    @patch("agent_reach.daily_run.intraday.record_morning_scan", return_value={"scan": {"scan_id": "S2"}})
    @patch("agent_reach.daily_run.workflows.save_morning_baseline")
    @patch("agent_reach.daily_run.workflows.run_morning")
    @patch("agent_reach.daily_run.snapshot_builder.build_and_save")
    @patch("agent_reach.daily_run.snapshot_builder.load_portfolio")
    def test_morning_manifest_has_harness_summary(
        self,
        mock_load,
        mock_build,
        mock_morning,
        mock_save_baseline,
        mock_morning_scan,
        mock_per_symbol,
        mock_trading_day,
        portfolio,
        tmp_path,
        monkeypatch,
    ):
        mock_load.return_value = portfolio
        mock_build.return_value = ({"code": "688008"}, tmp_path / "morning.json")
        mock_morning.return_value = {
            "snapshot": {"code": "688008"},
            "evaluation": {"report": {}},
            "harness_morning": {
                "job": "morning",
                "refinement_id": "ref_m",
                "changes": 1,
                "skipped": False,
            },
        }
        monkeypatch.setattr(
            "agent_reach.daily_run.run_manifest.runs_dir",
            lambda: tmp_path / "runs",
        )

        from agent_reach.daily_run.schedule import run_scheduled

        result = run_scheduled("morning", push=False)
        assert "harness_summary" in result
        assert result["harness_summary"]["total_changes"] >= 1
        manifest_files = list((tmp_path / "runs").rglob("morning_*.json"))
        assert manifest_files
        data = json.loads(manifest_files[0].read_text(encoding="utf-8"))
        assert data["payload"]["harness_summary"]["total_changes"] >= 1

    @patch("agent_reach.daily_run.trade_calendar.is_trading_day", return_value=(True, ""))
    @patch("agent_reach.daily_run.schedule._uses_per_symbol_jobs", return_value=False)
    @patch("agent_reach.daily_run.intraday.run_intraday")
    @patch("agent_reach.daily_run.intraday.should_evaluate_trade", return_value=False)
    @patch("agent_reach.daily_run.intraday.load_state")
    @patch("agent_reach.daily_run.snapshot_builder.build_and_save")
    @patch("agent_reach.daily_run.snapshot_builder.load_portfolio")
    def test_intraday_manifest_has_harness_summary(
        self,
        mock_load,
        mock_build,
        mock_load_state,
        mock_should_trade,
        mock_run_intraday,
        mock_per_symbol,
        mock_trading_day,
        portfolio,
        tmp_path,
        monkeypatch,
    ):
        mock_load.return_value = portfolio
        mock_build.return_value = ({"code": "688008"}, tmp_path / "intraday.json")
        mock_load_state.return_value = IntradayState(date="2026-08-17", scans=[], trades=[])
        mock_run_intraday.return_value = {
            "scan": {"scan_id": "S3", "mss_final": 48},
            "scan_count": 1,
        }

        with patch(
            "agent_reach.daily_run.intraday_harness.apply_intraday_harness_refinement",
            return_value={"job": "intraday", "refinement_id": "ref_i", "changes": 1, "skipped": False},
        ):
            monkeypatch.setattr(
                "agent_reach.daily_run.run_manifest.runs_dir",
                lambda: tmp_path / "runs",
            )
            from agent_reach.daily_run.schedule import run_scheduled

            result = run_scheduled("intraday", push=False)

        assert result["job"] == "intraday"
        assert result["harness_summary"]["total_changes"] >= 1

    @patch("agent_reach.daily_run.trade_calendar.is_trading_day", return_value=(True, ""))
    @patch("agent_reach.daily_run.schedule._uses_per_symbol_jobs", return_value=False)
    @patch("agent_reach.daily_run.workflows.run_close")
    @patch("agent_reach.daily_run.workflows.prepare_close_run")
    @patch("agent_reach.daily_run.workflows.load_morning_baseline")
    @patch("agent_reach.daily_run.intraday.load_state")
    @patch("agent_reach.daily_run.snapshot_builder.build_and_save")
    @patch("agent_reach.daily_run.snapshot_builder.load_portfolio")
    def test_close_manifest_has_harness_summary(
        self,
        mock_load_portfolio,
        mock_build,
        mock_load_state,
        mock_load_baseline,
        mock_prepare_close,
        mock_run_close,
        mock_per_symbol,
        mock_trading_day,
        portfolio,
        tmp_path,
        monkeypatch,
    ):
        mock_load_portfolio.return_value = portfolio
        snap = {"code": "688008", "mss_final": 48}
        mock_build.return_value = (snap, tmp_path / "close.json")
        mock_load_state.return_value = IntradayState(date="2026-08-17", scans=[], trades=[])
        mock_load_baseline.return_value = {"code": "688008", "mss_final": 52}
        mock_prepare_close.return_value = {
            "snapshot": snap,
            "portfolio": portfolio,
            "verify": {"verdict_current": "观察"},
            "steps": ["verify"],
        }
        mock_run_close.return_value = {
            "verify": {},
            "harness": {
                "layer_a": {"job": "close", "refinement_id": "ref_c", "changes": 2, "skipped": False},
            },
        }

        monkeypatch.setattr(
            "agent_reach.daily_run.run_manifest.runs_dir",
            lambda: tmp_path / "runs",
        )
        from agent_reach.daily_run.schedule import run_scheduled

        result = run_scheduled("close", push=False)
        assert result["harness_summary"]["total_changes"] >= 2

    @patch("agent_reach.daily_run.trade_calendar.is_trading_day", return_value=(True, ""))
    @patch("agent_reach.daily_run.workflows.run_weekly")
    @patch("agent_reach.daily_run.snapshot_builder.build_and_save")
    @patch("agent_reach.daily_run.snapshot_builder.load_portfolio")
    def test_weekly_manifest_has_harness_summary(
        self,
        mock_load,
        mock_build,
        mock_run_weekly,
        mock_trading_day,
        portfolio,
        tmp_path,
        monkeypatch,
    ):
        mock_load.return_value = portfolio
        mock_build.return_value = ({"code": "688008"}, tmp_path / "weekly.json")
        mock_run_weekly.return_value = {
            "steps": ["generate"],
            "harness": {
                "layer_a": {"job": "weekly", "refinement_id": "ref_w", "changes": 1, "skipped": False},
            },
        }
        monkeypatch.setattr(
            "agent_reach.daily_run.run_manifest.runs_dir",
            lambda: tmp_path / "runs",
        )

        from agent_reach.daily_run.schedule import run_scheduled

        result = run_scheduled("weekly", push=False)
        assert result["harness_summary"]["total_changes"] >= 1

# -*- coding: utf-8
"""Tests for morning/close one-click workflows."""

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from agent_reach.daily_run.settings import load_settings
from agent_reach.daily_run.workflows import (
    prepare_close_run,
    run_close,
    run_morning,
    save_morning_baseline,
)


@pytest.fixture
def morning_snapshot():
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "code": "688008",
        "name": "澜起科技",
        "price": 255.87,
        "ma20": 260.0,
        "position_20d": 0.55,
        "volume_ratio": 1.2,
        "mss_breakdown": {"fx": 35, "flow": 48, "global": 38, "sentiment": 50},
        "sources": {
            "quote": {"summary": "q"},
            "flow": {"summary": "f"},
            "sentiment": {"summary": "s"},
        },
        "structured_review_complete": True,
    }


def _settings_with_team(**team_overrides):
    cfg = load_settings()
    team = {**(cfg.get("team") or {}), **team_overrides}
    return {**cfg, "team": team}


@pytest.fixture
def portfolio():
    return {
        "total": 100000,
        "cash": 61000,
        "cash_ratio": 0.61,
        "holdings": [{"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87}],
        "watchlist": [
            {"code": "603986", "name": "兆易创新"},
            {"code": "002273", "name": "水晶光电"},
        ],
    }


class TestMorningWorkflow:
    @patch("agent_reach.daily_run.workflows._push_markdown", return_value={"code": 0, "data": {}})
    @patch("agent_reach.daily_run.workflows._send_start_notification")
    def test_run_morning_dry_pipeline(self, mock_start, mock_push, morning_snapshot):
        result = run_morning(morning_snapshot, settings=load_settings(), push=False, start_notify=False)
        assert "evaluate" in result["steps"]
        assert "team_first" not in result["steps"]
        assert result["steps"][0] in ("snapshot", "mss_experts")
        assert result["evaluation"]["report"]["verdict"]
        assert "Team-First" not in result.get("team_markdown", "")

    @patch("agent_reach.daily_run.workflows._push_markdown", return_value={"code": 0, "data": {}})
    @patch("agent_reach.daily_run.workflows._send_start_notification")
    def test_run_morning_with_experts(self, mock_start, mock_push, morning_snapshot):
        settings = _settings_with_team(enabled=True, morning_team_first=True)
        result = run_morning(morning_snapshot, settings=settings, push=False, start_notify=False)
        assert "team_first" in result["steps"]
        assert "Team-First" in result.get("team_markdown", "")

    @patch("agent_reach.daily_run.workflows.push_report_sections")
    @patch("agent_reach.daily_run.workflows._send_start_notification")
    def test_run_morning_push(self, mock_start, mock_push, morning_snapshot):
        mock_push.return_value = {"mode": "split", "count": 2, "feishu": {"code": 0}}
        result = run_morning(morning_snapshot, settings=load_settings(), push=True, start_notify=True)
        assert "push" in result["steps"]
        assert mock_push.called
        assert mock_start.called


class TestCloseWorkflow:
    def test_run_close_dry(self, morning_snapshot):
        baseline = dict(morning_snapshot)
        baseline["mss_final"] = 65
        baseline["verdict"] = "可做"
        baseline["mss_range"] = [45, 58]
        current = dict(morning_snapshot)
        current["mss_breakdown"] = {"fx": 35, "flow": 48, "global": 38, "sentiment": 50}
        result = run_close(current, baseline, settings=load_settings(), push=False)
        assert "verify" in result
        assert "Markdown" in result["markdown"] or "验证摘要" in result["markdown"]
        assert "portfolio_markdown" in result
        assert "个股盈亏" in result["portfolio_markdown"]

    def test_save_baseline(self, morning_snapshot, tmp_path):
        path = save_morning_baseline(morning_snapshot, path=tmp_path / "morning.json")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["code"] == "688008"

    @patch("agent_reach.daily_run.workflows.run_exa_research", return_value=[])
    @patch("agent_reach.daily_run.workflows._push_markdown", return_value={"code": 0, "data": {}})
    def test_run_close_includes_watchlist_and_code_review(
        self, mock_push, mock_research, morning_snapshot
    ):
        baseline = dict(morning_snapshot)
        baseline["mss_final"] = 65
        baseline["verdict"] = "可做"
        baseline["mss_range"] = [45, 58]
        current = dict(morning_snapshot)
        current["mss_breakdown"] = {"fx": 35, "flow": 48, "global": 38, "sentiment": 50}
        result = run_close(
            current,
            baseline,
            settings=load_settings(),
            push=False,
            watchlist_adjust={
                "applied": True,
                "message": "观察池调整 1 项（close）",
                "changes": [
                    {
                        "action": "add",
                        "code": "002273",
                        "name": "水晶光电",
                        "reason": "盘中卖出回收",
                    }
                ],
            },
            code_review={
                "findings": [],
                "fixes_applied": ["已重算 cash_ratio"],
                "portfolio_changed": True,
            },
        )
        assert "观察池调整" in result["markdown"]
        assert "002273" in result["markdown"]
        assert "代码走读" in result["markdown"]
        assert "已重算 cash_ratio" in result["markdown"]


class TestPrepareCloseRun:
    @patch("agent_reach.daily_run.snapshot_builder.save_portfolio")
    @patch("agent_reach.daily_run.close_code_review.run_close_code_review")
    @patch("agent_reach.daily_run.watchlist_manager.adjust_watchlist")
    @patch("agent_reach.daily_run.workflows.run_team_first")
    @patch("agent_reach.daily_run.workflows.verify_snapshots")
    def test_prepare_close_run_pipeline(
        self,
        mock_verify,
        mock_team,
        mock_adjust,
        mock_code_review,
        mock_save_pf,
        morning_snapshot,
        portfolio,
    ):
        from agent_reach.daily_run.close_code_review import CodeReviewResult
        from agent_reach.daily_run.verify import VerifyResult
        from agent_reach.daily_run.watchlist_manager import WatchlistAdjustResult

        baseline = dict(morning_snapshot)
        baseline["mss_final"] = 52
        current = dict(morning_snapshot)
        mock_team.side_effect = lambda snap, cfg, **kw: snap
        mock_verify.return_value = VerifyResult(
            code="688008",
            name="澜起科技",
            price_baseline=255.0,
            price_current=247.0,
            price_delta_pct=-0.03,
            mss_baseline=52.0,
            mss_current=48.0,
            mss_delta=-4.0,
            verdict_baseline="可做",
            verdict_current="观察",
            verdict_changed=True,
            mss_range_baseline=(45.0, 55.0),
            mss_within_prediction=True,
            summary="ok",
        )
        mock_adjust.return_value = WatchlistAdjustResult(
            applied=False,
            portfolio=portfolio,
            message="观察池无变更",
        )
        mock_code_review.return_value = CodeReviewResult(portfolio=portfolio)

        prepared = prepare_close_run(
            current,
            baseline,
            portfolio,
            settings=load_settings(),
            scans=[{"scan_id": "S1", "mss_final": 50}],
            trades=[],
        )
        assert "verify" in prepared["steps"]
        assert "code_review" in prepared["steps"]
        assert prepared["verify"] == prepared["pre_verify"]
        assert prepared["snapshot"].get("intraday_scans")
        mock_verify.assert_called_once()
        mock_team.assert_not_called()
        mock_adjust.assert_called_once()
        assert mock_adjust.call_args.kwargs.get("verify") is not None
        mock_save_pf.assert_not_called()

    @patch("agent_reach.daily_run.workflows.run_exa_research", return_value=[])
    @patch("agent_reach.daily_run.workflows.verify_snapshots")
    def test_run_close_reuses_prepared_verify(self, mock_verify, morning_snapshot):
        from agent_reach.daily_run.verify import VerifyResult

        baseline = dict(morning_snapshot)
        baseline["mss_final"] = 52
        baseline["verdict"] = "可做"
        baseline["mss_range"] = [45, 55]
        current = dict(morning_snapshot)
        current["team_review"] = {"consensus_score": 55}
        prepared_verify = VerifyResult(
            code="688008",
            name="澜起科技",
            price_baseline=255.0,
            price_current=255.87,
            price_delta_pct=0.003,
            mss_baseline=52.0,
            mss_current=48.0,
            mss_delta=-4.0,
            verdict_baseline="可做",
            verdict_current="观察",
            verdict_changed=True,
            mss_range_baseline=(45.0, 55.0),
            mss_within_prediction=True,
            summary="prepared once",
        ).to_dict()

        result = run_close(
            current,
            baseline,
            settings=load_settings(),
            push=False,
            verify_dict=prepared_verify,
        )
        mock_verify.assert_not_called()
        assert result["verify"]["summary"] == "prepared once"

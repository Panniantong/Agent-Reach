# -*- coding: utf-8
"""Tests for prior close MSS reference in morning reports."""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from agent_reach.daily_run.pipeline import build_report, render_markdown
from agent_reach.daily_run.prior_close import (
    attach_prior_close_reference,
    load_prior_close_reference,
    prev_trading_day,
    save_close_baseline,
)
from agent_reach.daily_run.settings import load_settings
from agent_reach.daily_run.trade_calendar import today_shanghai
from agent_reach.daily_run.verdict import VerdictResult


@pytest.fixture
def settings():
    return load_settings()


class TestPriorCloseReference:
    def test_save_and_load_close_baseline(self, tmp_path, monkeypatch):
        close_dir = tmp_path / "baselines" / "close"
        close_dir.mkdir(parents=True)

        def _path(code: str) -> Path:
            return close_dir / f"{code}.json"

        monkeypatch.setattr(
            "agent_reach.daily_run.prior_close.close_baseline_path",
            _path,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.prior_close.today_shanghai",
            lambda: date(2026, 7, 17),
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.prior_close.prev_trading_day",
            lambda *args, **kwargs: date(2026, 7, 17),
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.prior_close.runs_dir",
            lambda: tmp_path / "runs",
        )

        snap = {
            "code": "688008",
            "name": "澜起科技",
            "mss_final": 48.2,
            "mss_breakdown": {"fx": 35, "flow": 48, "global": 38, "sentiment": 50},
        }
        verify = {"mss_current": 48.2, "verdict_current": "观察", "name": "澜起科技"}
        save_close_baseline(snapshot=snap, verify=verify)

        loaded = load_prior_close_reference("688008", load_settings())
        assert loaded is not None
        assert loaded["mss_final"] == 48.2
        assert loaded["verdict"] == "观察"

    def test_attach_prior_close_to_premarket_snapshot(self, tmp_path, monkeypatch, settings):
        close_dir = tmp_path / "baselines" / "close"
        close_dir.mkdir(parents=True)
        today = today_shanghai()
        prior = today - timedelta(days=1)
        while prior.weekday() >= 5:
            prior -= timedelta(days=1)

        (close_dir / "688008.json").write_text(
            json.dumps(
                {
                    "code": "688008",
                    "name": "澜起科技",
                    "mss_final": 46.0,
                    "verdict": "观察",
                    "close_date": prior.isoformat(),
                }
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(
            "agent_reach.daily_run.prior_close.close_baseline_path",
            lambda code: close_dir / f"{code}.json",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.prior_close.prev_trading_day",
            lambda *a, **k: prior,
        )

        snap = attach_prior_close_reference(
            {"code": "688008", "name": "澜起科技", "report_type": "premarket"},
            settings,
        )
        assert snap["prior_close_mss"] == 46.0
        assert snap["prior_close_date"] == prior.isoformat()

    def test_render_markdown_shows_prior_close_delta(self, settings):
        report = build_report(
            {
                "code": "688008",
                "prior_close_mss": 46.0,
                "prior_close_date": "2026-07-16",
                "prior_close_verdict": "观察",
            },
            audit=type("A", (), {"passed": True, "summary": lambda self: "ok", "warnings": []})(),
            verdict=VerdictResult(
                verdict="观察",
                confidence="中",
                mss_final=44.5,
                entry_price=None,
                stop_loss_price=None,
                invalidation="test",
                reasoning="test",
            ),
            settings=settings,
        )
        md = render_markdown(report)
        assert "昨收 MSS" in md
        assert "46.0" in md
        assert "44.5" in md
        assert report["prior_close_delta"] == -1.5

    def test_prev_trading_day_skips_weekend(self):
        friday = date(2026, 7, 17)
        assert prev_trading_day(friday).weekday() < 5

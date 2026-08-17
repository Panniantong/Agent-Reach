# -*- coding: utf-8
"""Phase 5: Exa auto, trade calendar, channel experts, experience writeback."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_reach.daily_run.close_research import build_research_queries, render_research_markdown
from agent_reach.daily_run.exa_client import ExaError, _parse_mcporter_output, format_exa_error, summarize_hits
from agent_reach.daily_run.experience import append_experience_entry, load_recent_experience
from agent_reach.daily_run.settings import load_settings
from agent_reach.daily_run.trade_calendar import is_trading_day, is_weekend


class TestExaClient:
    def test_parse_json_results(self):
        raw = json.dumps([{"title": "Test", "url": "https://exa.ai", "snippet": "hello"}])
        hits = _parse_mcporter_output(raw)
        assert len(hits) == 1
        assert hits[0]["title"] == "Test"

    def test_summarize_hits(self):
        s = summarize_hits([{"title": "A"}, {"title": "B"}])
        assert "A" in s and "B" in s

    def test_format_exa_error_strips_stack(self):
        raw = "[mcporter] Ad-hoc servers require either --http-url or --stdio.\nError: ..."
        msg = format_exa_error(raw)
        assert "file://" not in msg
        assert "Exa 未配置" in msg or "Ad-hoc" not in msg

    @patch("agent_reach.daily_run.exa_client.subprocess.run")
    @patch("agent_reach.daily_run.exa_client.shutil.which", return_value="/usr/bin/mcporter")
    @patch("agent_reach.daily_run.exa_client.mcporter_cli_prefix")
    def test_web_search_uses_config_flag(self, mock_prefix, mock_which, mock_run, tmp_path):
        cfg = tmp_path / "mcporter.json"
        mock_prefix.return_value = ["mcporter", "--config", str(cfg)]
        mock_run.return_value = type(
            "R", (), {"returncode": 0, "stdout": '[{"title":"Hit","url":"https://x.com"}]', "stderr": ""}
        )()

        from agent_reach.daily_run.exa_client import web_search_exa

        hits = web_search_exa("test query", num_results=1, timeout=5)
        assert hits[0]["title"] == "Hit"
        cmd = mock_run.call_args[0][0]
        assert "--config" in cmd
        assert str(cfg) in cmd
        assert "--env" not in cmd


class TestTradeCalendar:
    def test_weekend(self):
        assert is_weekend(date(2026, 7, 11))  # Saturday

    @patch("agent_reach.daily_run.trade_calendar._load_trade_dates_akshare", return_value=set())
    @patch("agent_reach.daily_run.trade_calendar.load_holiday_overrides", return_value={"2026-07-08"})
    def test_holiday_skip(self, *_m):
        ok, reason = is_trading_day(date(2026, 7, 8), settings=load_settings())
        assert ok is False

    @patch("agent_reach.daily_run.trade_calendar._load_trade_dates_akshare")
    def test_akshare_calendar(self, mock_dates):
        mock_dates.return_value = {"2026-07-08", "2026-07-09"}
        ok, _ = is_trading_day(date(2026, 7, 8), settings=load_settings())
        assert ok is True
        ok2, _ = is_trading_day(date(2026, 7, 10), settings=load_settings())
        assert ok2 is False


class TestExperience:
    def test_append_experience(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.experience.experience_dir",
            lambda: tmp_path,
        )
        snap = {"code": "688008", "name": "澜起科技", "mss_final": 42}
        verify = {
            "verdict_current": "观察",
            "mss_within_prediction": True,
            "deviations": [],
            "recommendations": [],
        }
        result = append_experience_entry(snap, verify, settings=load_settings())
        assert result.path.exists()
        recent = load_recent_experience(5)
        assert len(recent) == 1


class TestCloseResearch:
    def test_render_template_fallback(self):
        snap = {
            "portfolio": {"holdings": [{"code": "688008", "name": "澜起科技"}]},
        }
        with patch("agent_reach.daily_run.close_research.is_exa_available", return_value=False):
            md = render_research_markdown(snap, research_results=[], settings=load_settings())
        assert "调研" in md
        assert build_research_queries(snap)


class TestChannelExperts:
    @patch("agent_reach.daily_run.plugins.macro_expert.search_exa_snippet", return_value="北向流入")
    def test_macro_channel_enrich(self, mock_exa):
        from agent_reach.daily_run.plugins.macro_expert import MacroExpert
        from agent_reach.daily_run.plugins.base import PluginContext

        ctx = PluginContext(
            snapshot={"mss_breakdown": {"fx": 40, "global": 45}, "code": "688008"},
            settings=load_settings(),
        )
        r = MacroExpert().run(ctx)
        assert r.details.get("channel_enriched") is True
        mock_exa.assert_called_once()

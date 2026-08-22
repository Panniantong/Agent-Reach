# -*- coding: utf-8
"""Tests for Phase-2/3 daily-run optimizations."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_reach.daily_run.baseline_fallback import load_close_baseline
from agent_reach.daily_run.close_improvements import generate_close_improvements
from agent_reach.daily_run.exa_cache import cached_web_search_exa, put_cached_search
from agent_reach.daily_run.experience import append_experience_entry
from agent_reach.daily_run.intraday_push import should_push_intraday
from agent_reach.daily_run.snapshot_cache import load_daily_cache, merge_technicals, save_daily_cache
from agent_reach.daily_run.weekly_digest import load_weekly_digest, save_weekly_digest
from agent_reach.daily_run.week_forecast import (
    _events_from_weekly_digest,
    _historical_vol_scale,
    generate_week_forecast,
)


class TestIntradayPush:
    def test_smart_mode_pushes_milestones(self):
        settings = {"schedule": {"intraday_push_mode": "smart"}}
        assert should_push_intraday("S1", settings=settings) is True
        assert should_push_intraday("S5", settings=settings, trade_happened=False) is False

    def test_trade_only(self):
        settings = {"schedule": {"intraday_push_mode": "trade_only"}}
        assert should_push_intraday("S1", settings=settings, trade_happened=False) is False
        assert should_push_intraday("S3", settings=settings, trade_happened=True) is True


class TestWeeklyDigest:
    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.weekly_digest.digest_path",
            lambda: tmp_path / "weekly_digest.json",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.weekly_digest.today_shanghai",
            lambda: date(2026, 7, 11),
        )
        report = {
            "week_end": "2026-07-10",
            "hot_sectors": [{"sector": "半导体", "avg_change_pct": 2.1}],
            "sector_research": [{"label": "AI", "summary": "test"}],
            "macro_signals": {
                "hot_stocks": [{"name": "澜起科技", "symbol": "688008"}],
                "xueqiu_exa_research": [{"label": "存储", "summary": "景气延续"}],
            },
            "watchlist_intel": {
                "603986": {
                    "name": "兆易创新",
                    "announcements": [{"title": "业绩预告"}],
                }
            },
        }
        save_weekly_digest(report)
        loaded = load_weekly_digest()
        assert loaded is not None
        assert loaded["hot_sectors"][0]["sector"] == "半导体"
        assert loaded["macro_signals"]["hot_stocks"][0]["name"] == "澜起科技"
        assert loaded["watchlist_intel"]["603986"]["name"] == "兆易创新"
        assert loaded["xueqiu_exa_research"][0]["label"] == "存储"

    def test_events_from_digest(self):
        events = _events_from_weekly_digest(
            {
                "hot_sectors": [{"sector": "新能源", "avg_change_pct": 1.5}],
                "sector_research": [{"label": "锂电", "summary": "景气"}],
            }
        )
        assert len(events) >= 2
        assert events[0]["source"] == "weekly_digest"


class TestBaselineFallback:
    def test_fallback_from_scan(self, tmp_path, monkeypatch):
        baseline_path = tmp_path / "last_morning.json"
        monkeypatch.setattr(
            "agent_reach.daily_run.baseline_fallback.default_baseline_path",
            lambda: baseline_path,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.baseline_fallback.load_last_snapshot",
            lambda: None,
        )
        scans = [{"code": "688008", "name": "测试", "mss_final": 45.0, "as_of": "2026-07-10T01:00:00Z"}]
        snap, source = load_close_baseline(scans=scans)
        assert source == "intraday_first_scan"
        assert snap["mss_final"] == 45.0


class TestExaCache:
    def test_cached_search(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.exa_cache.exa_cache_dir",
            lambda: tmp_path,
        )
        put_cached_search("test query", [{"title": "hit"}])
        hits, cached = cached_web_search_exa(
            "test query",
            settings={"exa_cache": {"enabled": True, "ttl_seconds": 3600}},
        )
        assert cached is True
        assert hits[0]["title"] == "hit"


class TestSnapshotCache:
    def test_daily_cache_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.snapshot_cache.cache_dir",
            lambda: tmp_path,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.snapshot_cache.today_shanghai",
            lambda: date(2026, 7, 10),
        )
        save_daily_cache({"macro_ctx": {"macro_summary": "ok"}})
        data = load_daily_cache()
        assert data["macro_ctx"]["macro_summary"] == "ok"

    def test_merge_technicals_preserves_existing_symbols(self):
        merged = merge_technicals(
            {
                "688008": {"ma20": 256.22, "position_20d": 0.55},
                "002273": {"ma20": 32.32},
            },
            {
                "002583": {"ma20": 7.95},
                "000725": {},
            },
        )
        assert merged["688008"]["ma20"] == 256.22
        assert merged["002273"]["ma20"] == 32.32
        assert merged["002583"]["ma20"] == 7.95
        assert "000725" not in merged

    def test_save_daily_cache_merges_technicals_across_runs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.snapshot_cache.cache_dir",
            lambda: tmp_path,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.snapshot_cache.today_shanghai",
            lambda: date(2026, 7, 10),
        )
        save_daily_cache({"technicals": {"688008": {"ma20": 256.22}}})
        save_daily_cache({"technicals": {"002273": {"ma20": 32.32}}})
        save_daily_cache({"technicals": {"000725": {}}})
        data = load_daily_cache()
        assert data["technicals"]["688008"]["ma20"] == 256.22
        assert data["technicals"]["002273"]["ma20"] == 32.32
        assert "000725" not in data["technicals"]


class TestExperienceForecast:
    def test_append_with_forecast_review(self, tmp_path, monkeypatch):
        exp_dir = tmp_path / "experience"
        monkeypatch.setattr(
            "agent_reach.daily_run.experience.experience_dir",
            lambda: exp_dir,
        )
        append_experience_entry(
            {"code": "688008", "name": "测试"},
            {"verdict_current": "观察", "mss_current": 50},
            settings={"experience": {"enabled": True}},
            forecast_review={
                "date": "2026-07-10",
                "accuracy": 0.3,
                "symbol_hits": 1,
                "symbol_total": 3,
                "mss_hit": False,
            },
        )
        line = (exp_dir / "experience.jsonl").read_text(encoding="utf-8").strip()
        entry = json.loads(line)
        assert entry["forecast_review"]["accuracy"] == 0.3
        assert any("命中率" in r for r in entry["rules"])


class TestCloseImprovementsForecast:
    def test_low_accuracy_suggestion(self):
        result = generate_close_improvements(
            baseline={},
            current={"portfolio": {"holdings": [], "cash_ratio": 0.5}, "watchlist": []},
            verify={"verdict_current": "观察"},
            settings={"close_improvements": {"enabled": True}, "week_forecast": {"enabled": True}},
            forecast_review={
                "accuracy": 0.25,
                "symbol_hits": 1,
                "symbol_total": 4,
                "mss_hit": False,
                "mss_predicted": [40, 50],
                "mss_actual": 35,
            },
        )
        titles = [i.title for i in result.items]
        assert any("命中率" in t for t in titles)


class TestWeekForecastEnhancements:
    def test_historical_vol_scale(self, tmp_path, monkeypatch):
        fc_dir = tmp_path / "forecasts"
        fc_dir.mkdir()
        fc_path = fc_dir / "2026-07-07.json"
        fc_path.write_text(
            json.dumps(
                {
                    "reviews": [
                        {
                            "symbol_evals": [
                                {"error_pct": 3.5},
                                {"error_pct": -4.0},
                            ]
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr("agent_reach.daily_run.week_forecast.forecasts_dir", lambda: fc_dir)
        scale = _historical_vol_scale({"vol_scale": 1.0})
        assert scale > 1.0

    @patch("agent_reach.daily_run.week_forecast.run_news_research", return_value=[])
    @patch("agent_reach.daily_run.weekly_digest.load_weekly_digest")
    @patch("agent_reach.daily_run.week_forecast.today_shanghai")
    def test_generate_uses_digest(self, mock_today, mock_digest, mock_news):
        mock_today.return_value = date(2026, 7, 12)
        mock_digest.return_value = {
            "week_end": "2026-07-10",
            "hot_sectors": [{"sector": "芯片", "avg_change_pct": 2.0}],
            "sector_research": [{"label": "半导体", "summary": "强势"}],
        }
        snapshot = {
            "portfolio": {"holdings": [], "watchlist": []},
            "macro_summary": "test",
        }
        forecast = generate_week_forecast(
            snapshot,
            {"week_forecast": {"enabled": True, "exa_news_research": False, "reuse_weekly_digest_exa": True}},
        )
        assert any("digest" in n for n in forecast.notes)
        assert any(e.get("source") == "weekly_digest" for e in forecast.news_events)

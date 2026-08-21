# -*- coding: utf-8
"""Tests for snapshot builder and schedule helpers."""

import json
from unittest.mock import patch

import pytest

from agent_reach.daily_run.quote_fetch import QuoteFetchResult
from agent_reach.daily_run.schedule import default_entries, render_crontab_block
from agent_reach.daily_run.snapshot_builder import (
    _apply_cached_technicals,
    _attach_technicals,
    _backfill_missing_technicals,
    _estimate_position_20d,
    _fallback_technicals_patch,
    _refresh_intraday_technicals,
    build_snapshot,
    code_to_xueqiu_symbol,
    load_portfolio,
)


@pytest.fixture
def portfolio():
    return {
        "primary_code": "688008",
        "total": 91938,
        "cash_ratio": 0.61,
        "mss_breakdown": {"fx": 35, "flow": 48, "global": 38, "sentiment": 50},
        "holdings": [
            {"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87},
            {"code": "002273", "name": "水晶光电", "shares": 300, "cost": 33.81},
        ],
        "watchlist": [{"code": "603986", "name": "兆易创新"}],
        "sources_overrides": {
            "flow": {"summary": "北向净流入"},
            "sentiment": {"summary": "DDR5 讨论"},
        },
    }


class TestSnapshotBuilder:
    def test_code_to_xueqiu_symbol(self):
        assert code_to_xueqiu_symbol("688008") == "SH688008"
        assert code_to_xueqiu_symbol("002273") == "SZ002273"

    @patch("agent_reach.daily_run.snapshot_builder.load_daily_cache")
    @patch("agent_reach.daily_run.snapshot_builder.collect_macro_context")
    @patch("agent_reach.daily_run.snapshot_builder.fetch_quotes_result")
    def test_build_snapshot_intraday_reuses_merged_technicals(
        self, mock_fetch_result, mock_macro, mock_cache, portfolio
    ):
        mock_cache.return_value = {
            "technicals": {
                "688008": {"ma20": 256.22, "position_20d": 0.55},
                "002273": {"ma20": 32.32},
            }
        }
        mock_macro.return_value = {
            "mss_breakdown": {"fx": 40, "flow": 50, "global": 45, "sentiment": 48},
            "sources": {},
            "macro_summary": "live macro",
        }
        mock_fetch_result.return_value = QuoteFetchResult(
            quotes={
                "688008": {"code": "688008", "name": "澜起科技", "price": 260.0, "change_pct": 1.5, "source": "xueqiu"},
                "002273": {"code": "002273", "name": "水晶光电", "price": 27.0, "change_pct": 0.2, "source": "xueqiu"},
                "603986": {"code": "603986", "name": "兆易创新", "price": 450.0, "change_pct": -3.0, "source": "xueqiu"},
            },
            sources_used=["xueqiu"],
        )
        with patch("agent_reach.daily_run.snapshot_builder._backfill_missing_technicals") as mock_backfill:
            mock_backfill.side_effect = lambda codes, quote_map, cached, **kwargs: cached
            snap = build_snapshot(
                portfolio,
                report_type="intraday",
                primary_code="002273",
                settings={"snapshot": {"intraday_enrich_level": "quotes"}},
            )
        assert snap["ma20"] == 32.32
        assert snap["portfolio"]["holdings"][0]["ma20"] == 256.22

    @patch("agent_reach.daily_run.snapshot_builder.load_daily_cache", return_value={})
    @patch("agent_reach.daily_run.snapshot_builder.collect_macro_context")
    @patch("agent_reach.daily_run.snapshot_builder.fetch_quotes_result")
    def test_build_snapshot_enriched(self, mock_fetch_result, mock_macro, _mock_cache, portfolio):
        mock_macro.return_value = {
            "mss_breakdown": {"fx": 40, "flow": 50, "global": 45, "sentiment": 48},
            "sources": {
                "flow": {"summary": "北向净流入 12 亿"},
                "sentiment": {"summary": "DDR5 讨论"},
            },
            "macro_summary": "live macro",
        }
        result = QuoteFetchResult(
            quotes={
                "688008": {
                    "code": "688008",
                    "name": "澜起科技",
                    "price": 260.0,
                    "change_pct": 1.5,
                    "source": "xueqiu",
                }
            },
            sources_used=["xueqiu"],
        )
        mock_fetch_result.return_value = result
        with patch("agent_reach.daily_run.snapshot_builder._attach_technicals") as mock_tech:
            mock_tech.return_value = {
                "code": "688008",
                "name": "澜起科技",
                "price": 260.0,
                "change_pct": 1.5,
                "ma20": 255.0,
                "position_20d": 0.55,
                "volume_ratio": 1.1,
                "source": "xueqiu",
            }
            snap = build_snapshot(portfolio, enrich=True)
        assert snap["code"] == "688008"
        assert snap["price"] == 260.0
        assert snap.get("quote_fetch", {}).get("coverage_pct", 0) >= 0
        assert snap["sources"]["flow"]["summary"] != "待更新"

    def test_load_portfolio_empty_falls_back_to_repo(self, tmp_path):
        from agent_reach.daily_run.snapshot_builder import repo_portfolio_path

        empty = tmp_path / "portfolio.json"
        empty.write_text(json.dumps({"holdings": [], "watchlist": []}), encoding="utf-8")
        data = load_portfolio(empty)
        if repo_portfolio_path().exists():
            assert data.get("holdings")
        else:
            assert data.get("holdings") or data.get("watchlist")

    @patch("agent_reach.daily_run.snapshot_builder.load_last_snapshot", return_value=None)
    @patch("agent_reach.daily_run.snapshot_builder.fetch_quotes_map", return_value={})
    def test_build_snapshot_no_enrich(self, mock_fetch, mock_last, portfolio):
        snap = build_snapshot(portfolio, enrich=False)
        assert snap["code"] == "688008"
        assert snap.get("enrich_level") == "lite"
        # lite mode still refreshes quotes (may differ from static cost)
        assert snap.get("price") is not None

    def test_fallback_technicals_patch_uses_portfolio_ma20(self):
        patch = _fallback_technicals_patch(
            "688008",
            {"price": 260.0},
            row={"ma20": 255.0},
        )
        assert patch["ma20"] == 255.0
        assert patch["position_20d"] is not None

    def test_estimate_position_20d_moves_with_price(self):
        ma20 = 255.0
        low = _estimate_position_20d(250.0, ma20)
        high = _estimate_position_20d(265.0, ma20)
        assert low is not None and high is not None
        assert high > low

    def test_refresh_intraday_technicals_recomputes_position(self):
        quote_map = {
            "688008": {
                "code": "688008",
                "price": 265.0,
                "ma20": 255.0,
                "position_20d": 0.55,
                "volume_ratio": 1.3,
            }
        }
        _refresh_intraday_technicals(quote_map)
        assert quote_map["688008"]["position_20d"] != 0.55
        assert quote_map["688008"]["volume_ratio"] == 1.3

    def test_apply_cached_technicals_preserves_live_volume_and_position(self):
        quote_map = {
            "688008": {
                "code": "688008",
                "price": 265.0,
                "ma20": 255.0,
                "volume_ratio": 1.3,
            }
        }
        cached = {"688008": {"ma20": 255.0, "position_20d": 0.55, "volume_ratio": 0.9}}
        _apply_cached_technicals(quote_map, cached, settings={"snapshot": {"intraday_refresh_technicals": True}})
        assert quote_map["688008"]["volume_ratio"] == 1.3
        assert quote_map["688008"]["position_20d"] != 0.55

    @patch("agent_reach.daily_run.snapshot_builder.load_daily_cache")
    @patch("agent_reach.daily_run.snapshot_builder.collect_macro_context")
    @patch("agent_reach.daily_run.snapshot_builder.fetch_quotes_result")
    def test_build_snapshot_intraday_refreshes_position_from_price(
        self, mock_fetch_result, mock_macro, mock_cache, portfolio
    ):
        mock_cache.return_value = {
            "technicals": {
                "002273": {"ma20": 32.32, "position_20d": 0.55},
            }
        }
        mock_macro.return_value = {
            "mss_breakdown": {"fx": 40, "flow": 50, "global": 45, "sentiment": 48},
            "sources": {},
            "macro_summary": "live macro",
        }
        mock_fetch_result.return_value = QuoteFetchResult(
            quotes={
                "688008": {"code": "688008", "name": "澜起科技", "price": 260.0, "change_pct": 1.5, "source": "xueqiu"},
                "002273": {"code": "002273", "name": "水晶光电", "price": 27.0, "change_pct": 0.2, "source": "xueqiu"},
                "603986": {"code": "603986", "name": "兆易创新", "price": 450.0, "change_pct": -3.0, "source": "xueqiu"},
            },
            sources_used=["xueqiu"],
        )
        with patch("agent_reach.daily_run.snapshot_builder._backfill_missing_technicals") as mock_backfill:
            mock_backfill.side_effect = lambda codes, quote_map, cached, **kwargs: cached
            snap = build_snapshot(
                portfolio,
                report_type="intraday",
                primary_code="002273",
                settings={
                    "snapshot": {
                        "intraday_enrich_level": "quotes",
                        "intraday_refresh_technicals": True,
                    }
                },
            )
        assert snap["ma20"] == 32.32
        assert snap["position_20d"] == _estimate_position_20d(27.0, 32.32)

    def test_fallback_technicals_patch_uses_cost_when_ma20_missing(self):
        patch = _fallback_technicals_patch(
            "688008",
            {"price": 260.0},
            row={"cost": 255.87},
        )
        assert patch["ma20"] == 255.87

    def test_fallback_technicals_patch_respects_cost_fallback_disabled(self):
        patch = _fallback_technicals_patch(
            "688008",
            {"price": 260.0},
            row={"cost": 255.87},
            settings={"snapshot": {"technicals_cost_fallback": False}},
        )
        assert patch == {}

    @patch("agent_reach.daily_run.xueqiu_technicals.fetch_technicals", side_effect=RuntimeError("xq down"))
    @patch("agent_reach.daily_run.akshare_adapter.fetch_technicals", side_effect=RuntimeError("network"))
    def test_attach_technicals_falls_back_to_portfolio_ma20(self, _mock_fetch, _mock_xq):
        out = _attach_technicals(
            {"code": "688008", "price": 260.0},
            "688008",
            fallback_row={"ma20": 255.0},
        )
        assert out["ma20"] == 255.0
        assert out["position_20d"] is not None

    @patch(
        "agent_reach.daily_run.xueqiu_technicals.fetch_technicals",
        return_value={
            "ma5": 6.05,
            "ma20": 5.84,
            "position_20d": 0.42,
            "volume_ratio": 0.82,
            "history_days": 25,
            "technicals_source": "xueqiu",
        },
    )
    @patch("agent_reach.daily_run.akshare_adapter.fetch_technicals", side_effect=RuntimeError("network"))
    def test_attach_technicals_falls_back_to_xueqiu_without_portfolio_row(
        self,
        _mock_ak,
        _mock_xq,
    ):
        out = _attach_technicals({"code": "000725", "price": 5.9}, "000725")
        assert out["ma20"] == 5.84
        assert out["volume_ratio"] == 0.82
        assert out["technicals_source"] == "xueqiu"

    @patch(
        "agent_reach.daily_run.xueqiu_technicals.fetch_technicals",
        return_value={"ma20": 5.84, "ma5": 6.05, "position_20d": 0.4, "volume_ratio": 0.8},
    )
    @patch("agent_reach.daily_run.akshare_adapter.fetch_technicals", side_effect=RuntimeError("network"))
    def test_attach_technicals_uses_xueqiu_before_portfolio_row(self, _mock_ak, mock_xq):
        out = _attach_technicals(
            {"code": "688008", "price": 260.0},
            "688008",
            fallback_row={"ma20": 255.0},
        )
        assert out["ma20"] == 5.84
        mock_xq.assert_called_once()

    @patch("agent_reach.daily_run.snapshot_cache.save_daily_cache")
    @patch("agent_reach.daily_run.xueqiu_technicals.fetch_technicals", side_effect=RuntimeError("xq down"))
    @patch("agent_reach.daily_run.akshare_adapter.fetch_technicals", side_effect=RuntimeError("network"))
    def test_backfill_missing_technicals_uses_cost_fallback(self, _mock_fetch, _mock_xq, _mock_save, portfolio):
        quote_map = {
            "688008": {"code": "688008", "price": 260.0},
            "002273": {"code": "002273", "price": 27.0},
        }
        source_rows = {
            "688008": portfolio["holdings"][0],
            "002273": portfolio["holdings"][1],
        }
        updated = _backfill_missing_technicals(
            ["688008", "002273"],
            quote_map,
            {},
            source_rows=source_rows,
        )
        assert updated["688008"]["ma20"] == 255.87
        assert updated["002273"]["ma20"] == 33.81
        assert quote_map["688008"]["ma20"] == 255.87


class TestSchedule:
    def test_render_crontab_block(self):
        block = render_crontab_block()
        assert "agent-reach daily-run schedule BEGIN" in block
        assert "Asia/Shanghai" in block
        assert "daily-run-local-cron.sh" in block
        assert "SHELL=/bin/bash" in block
        assert "daily-run-local-cron.sh morning" in block
        assert "daily-run-local-cron.sh close" in block
        assert "0 18 * * 1-5" in block
        assert "S15/15" in block
        assert block.count("daily-run-local-cron.sh intraday") == 14

    def test_default_entries_count(self):
        assert len(default_entries()) == 18  # premarket + morning + 13 scans + close + weekly + forecast

    @patch("agent_reach.daily_run.intraday.record_morning_scan", return_value={"scan": {"scan_id": "S1"}})
    @patch("agent_reach.daily_run.trade_calendar.is_trading_day", return_value=(True, ""))
    @patch("agent_reach.daily_run.workflows.save_morning_baseline")
    @patch("agent_reach.daily_run.workflows.run_morning")
    @patch("agent_reach.daily_run.snapshot_builder.build_and_save")
    @patch("agent_reach.daily_run.snapshot_builder.load_portfolio")
    @patch("agent_reach.daily_run.schedule._uses_per_symbol_jobs", return_value=False)
    def test_run_scheduled_morning(
        self,
        mock_per_symbol,
        mock_load,
        mock_build,
        mock_morning,
        mock_save_baseline,
        mock_trading_day,
        mock_morning_scan,
        portfolio,
        tmp_path,
    ):
        mock_load.return_value = portfolio
        mock_build.return_value = ({"code": "688008"}, tmp_path / "snap.json")
        mock_morning.return_value = {"snapshot": {"code": "688008"}, "evaluation": {"report": {}}}

        from agent_reach.daily_run.schedule import run_scheduled

        result = run_scheduled("morning", push=False)
        assert result["job"] == "morning"
        mock_save_baseline.assert_called_once()
        mock_morning_scan.assert_called_once()
        assert "harness_summary" in result

    @patch("agent_reach.daily_run.intraday_harness.apply_intraday_harness_refinement")
    @patch("agent_reach.daily_run.intraday.record_morning_scan", return_value={"scan": {"scan_id": "S1"}})
    @patch("agent_reach.daily_run.trade_calendar.is_trading_day", return_value=(True, ""))
    @patch("agent_reach.daily_run.workflows.save_morning_baseline")
    @patch("agent_reach.daily_run.workflows.run_morning")
    @patch("agent_reach.daily_run.snapshot_builder.build_and_save")
    @patch("agent_reach.daily_run.snapshot_builder.load_portfolio")
    @patch("agent_reach.daily_run.schedule._uses_per_symbol_jobs", return_value=False)
    def test_run_scheduled_morning_skips_intraday_harness(
        self,
        mock_per_symbol,
        mock_load,
        mock_build,
        mock_morning,
        mock_save_baseline,
        mock_trading_day,
        mock_morning_scan,
        mock_intraday_harness,
        portfolio,
        tmp_path,
    ):
        mock_load.return_value = portfolio
        mock_build.return_value = ({"code": "688008"}, tmp_path / "snap.json")
        mock_morning.return_value = {
            "snapshot": {"code": "688008"},
            "evaluation": {"report": {}},
            "harness_morning": {"refinement_id": "ref_m", "changes": 1, "skipped": False, "job": "morning"},
        }

        from agent_reach.daily_run.schedule import run_scheduled

        result = run_scheduled("morning", push=False)
        mock_intraday_harness.assert_not_called()
        assert result["harness_summary"]["total_changes"] >= 1

    @patch("agent_reach.daily_run.schedule._uses_per_symbol_jobs", return_value=False)
    @patch("agent_reach.daily_run.trade_calendar.is_trading_day", return_value=(True, ""))
    @patch("agent_reach.daily_run.workflows.run_close")
    @patch("agent_reach.daily_run.workflows.prepare_close_run")
    @patch("agent_reach.daily_run.workflows.load_morning_baseline")
    @patch("agent_reach.daily_run.intraday.load_state")
    @patch("agent_reach.daily_run.snapshot_builder.build_and_save")
    @patch("agent_reach.daily_run.snapshot_builder.load_portfolio")
    def test_run_scheduled_close(
        self,
        mock_load_portfolio,
        mock_build,
        mock_load_state,
        mock_load_baseline,
        mock_prepare_close,
        mock_run_close,
        _mock_per_symbol,
        portfolio,
        tmp_path,
    ):
        from agent_reach.daily_run.intraday import IntradayState

        mock_load_portfolio.return_value = portfolio
        snap = {"code": "688008", "mss_final": 48}
        mock_build.return_value = (snap, tmp_path / "close.json")
        mock_load_state.return_value = IntradayState(
            date="2026-07-10",
            scans=[{"scan_id": "S1", "mss_final": 50}, {"scan_id": "S2", "mss_final": 48}],
            trades=[],
        )
        mock_load_baseline.return_value = {"code": "688008", "mss_final": 52, "mss_range": [45, 55]}
        mock_prepare_close.return_value = {
            "snapshot": snap,
            "portfolio": portfolio,
            "verify": {"verdict_current": "观察", "summary": "ok"},
            "pre_verify": {"verdict_current": "观察", "summary": "ok"},
            "watchlist_adjust": {"applied": False, "message": "观察池无变更", "changes": []},
            "code_review": {"findings": [], "fixes_applied": [], "portfolio_changed": False},
            "steps": ["team_first", "verify", "code_review"],
        }
        mock_run_close.return_value = {"verify": {}, "markdown": "close"}

        from agent_reach.daily_run.schedule import run_scheduled

        result = run_scheduled("close", push=False)
        assert result["job"] == "close"
        mock_prepare_close.assert_called_once()
        mock_run_close.assert_called_once()
        assert snap.get("intraday_scans")
        assert result["result"]["code_review"] is not None
        assert result["result"]["prepare_steps"] == ["team_first", "verify", "code_review"]


class TestRunManifest:
    def test_save_run_manifest_serializes_audit_result(self, tmp_path, monkeypatch):
        from agent_reach.daily_run.auditor import AuditResult
        from agent_reach.daily_run.run_manifest import save_run_manifest

        monkeypatch.setattr(
            "agent_reach.daily_run.run_manifest.runs_dir",
            lambda: tmp_path,
        )
        audit = AuditResult(passed=True, issues=[], warnings=["warn"])
        path = save_run_manifest(
            "intraday",
            {"evaluation": {"audit": audit, "report": {"verdict": "观察"}}},
            duration_ms=12.5,
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["payload"]["evaluation"]["audit"]["passed"] is True
        assert data["payload"]["evaluation"]["audit"]["warnings"] == ["warn"]

    def test_save_run_manifest_uses_shanghai_date_dir(self, tmp_path, monkeypatch):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from agent_reach.daily_run.run_manifest import save_run_manifest

        monkeypatch.setattr(
            "agent_reach.daily_run.run_manifest.runs_dir",
            lambda: tmp_path,
        )
        sh = ZoneInfo("Asia/Shanghai")
        fake_now = datetime(2026, 7, 11, 7, 30, 0, tzinfo=sh)
        monkeypatch.setattr(
            "agent_reach.daily_run.run_manifest._manifest_shanghai_now",
            lambda: fake_now,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.run_manifest.today_shanghai",
            lambda: fake_now.date(),
        )
        path = save_run_manifest("morning", {"job": "morning"})
        assert path.parent.name == "2026-07-11"
        assert path.name.startswith("morning_0730")

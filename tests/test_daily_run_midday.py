# -*- coding: utf-8
"""Tests for 12:30 midday refresh workflow."""

from unittest.mock import patch

from agent_reach.daily_run.midday import (
    apply_midday_macro_refresh,
    midday_cfg,
    render_midday_markdown,
    run_midday,
)
from agent_reach.daily_run.schedule import INTRADAY_MAX_SCANS, default_entries


def test_intraday_max_scans_includes_midday():
    assert INTRADAY_MAX_SCANS == 16


def test_default_crontab_has_midday():
    labels = [e.label for e in default_entries()]
    assert any("午盘" in label and "12:30" in label for label in labels)


def test_midday_cfg_enabled_by_default():
    assert midday_cfg({})["enabled"] is True


def test_apply_midday_macro_refresh_merges():
    snapshot = {
        "portfolio": {"holdings": [], "watchlist": []},
        "mss_breakdown": {"fx": 40, "flow": 40, "global": 40, "sentiment": 40},
        "sources": {},
    }
    macro = {
        "macro_summary": "北向 +12 亿",
        "macro_signals": {"northbound_flow_yi": 12.0},
        "mss_breakdown": {"flow": 55, "global": 48, "sentiment": 52},
        "sources": {"flow": {"summary": "北向净流入 12 亿"}},
    }
    with patch(
        "agent_reach.daily_run.macro_collector.collect_macro_context",
        return_value=macro,
    ), patch(
        "agent_reach.daily_run.macro_collector.enrich_macro_sources",
        side_effect=lambda _pf, sources, _cfg: sources,
    ), patch(
        "agent_reach.daily_run.snapshot_cache.load_daily_cache",
        return_value={},
    ), patch(
        "agent_reach.daily_run.snapshot_cache.save_daily_cache",
    ) as mock_save:
        out = apply_midday_macro_refresh(snapshot, settings={})
    assert out["macro_summary"] == "北向 +12 亿"
    assert out["mss_breakdown"]["flow"] == 55
    mock_save.assert_called_once()


@patch("agent_reach.daily_run.midday.apply_midday_macro_refresh", side_effect=lambda s, **_: s)
@patch("agent_reach.daily_run.intraday.record_scan_from_evaluation")
@patch("agent_reach.daily_run.pipeline.evaluate_snapshot")
def test_run_midday_records_source_midday(mock_eval, mock_record, _mock_macro):
    mock_eval.return_value = {
        "audit": type("A", (), {"passed": True, "warnings": []})(),
        "report": {"verdict": "观察", "mss_final": 44, "reasoning": "午后宜观望"},
        "gate": type("G", (), {"passed": True, "downgraded": False, "missing_fields": []})(),
        "verdict": type("V", (), {"verdict": "观察"})(),
    }
    mock_record.return_value = {
        "scan": {"scan_id": "S10", "mss_final": 44, "verdict": "观察", "source": "midday"},
        "state": {"scans": [{"scan_id": "S10", "source": "midday"}]},
        "lookback_mss": 43.5,
        "lookback_detail": [{"scan_id": "S10", "mss_final": 44, "weight": 1.0, "weighted": 44}],
        "trend": "flat",
        "xueqiu_cross": {},
    }
    result = run_midday(
        {"code": "688008", "name": "澜起", "portfolio": {}},
        settings={"midday": {"enabled": True}},
        push=False,
    )
    assert mock_record.call_args.kwargs["source"] == "midday"
    assert "record_scan" in result["steps"]
    assert "午盘分析" in result["markdown"]


def test_render_midday_markdown_sections():
    md = render_midday_markdown(
        {
            "scan": {"scan_id": "S10", "mss_final": 44, "verdict": "观察"},
            "evaluation": {"report": {"reasoning": "午后观望"}},
            "lookback_mss": 43.5,
            "lookback_detail": [{"scan_id": "S10", "mss_final": 44, "weight": 1.0, "weighted": 44}],
            "trend": "flat",
            "state": {"scans": [{"scan_id": "S10", "source": "midday", "mss_final": 44}]},
            "enriched": {"macro_summary": "午休宏观 refresh"},
            "xueqiu_cross": {},
        }
    )
    assert "午盘分析" in md
    assert "上午回顾" in md
    assert "午休宏观刷新" in md
    assert "午后 Lookback" in md

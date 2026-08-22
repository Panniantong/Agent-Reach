# -*- coding: utf-8
"""Tests for close review improvement suggestions."""

from agent_reach.daily_run.close_improvements import (
    CloseImprovements,
    expected_scan_slots,
    generate_close_improvements,
    render_improvements_markdown,
)
from agent_reach.daily_run.settings import load_settings


def test_expected_scan_slots_count():
    slots = expected_scan_slots()
    assert len(slots) == 16
    assert slots[0]["scan_id"] == "S1"
    assert slots[0]["time"] == "07:00"
    assert slots[1]["scan_id"] == "S2"
    assert slots[1]["time"] == "08:00"
    assert slots[2]["scan_id"] == "S3"
    assert slots[2]["time"] == "09:00"
    assert slots[3]["scan_id"] == "S4"
    assert slots[3]["time"] == "09:30"
    assert slots[4]["scan_id"] == "S5"
    assert slots[4]["time"] == "09:54"


def test_render_improvements_empty_when_enabled():
    md = render_improvements_markdown(CloseImprovements(), enabled=True)
    assert "复盘改进意见" in md
    assert "暂无专项调参建议" in md


def test_schedule_drift_matches_by_scan_id():
    settings = load_settings()
    baseline = {"mss_range": [40, 52], "mss_final": 48, "price": 100}
    current = {"mss_final": 48, "portfolio": {"cash_ratio": 0.5, "holdings": []}, "watchlist": []}
    verify = {"mss_within_prediction": True, "verdict_current": "观察"}
    # S2 missing — only S1 and S3; drift check must not compare S3 to S2 slot
    scans = [
        {"scan_id": "S1", "as_of": "2026-07-08T23:00:00+00:00", "mss_final": 48},
        {"scan_id": "S3", "as_of": "2026-07-08T03:30:00+00:00", "mss_final": 46},
    ]
    result = generate_close_improvements(
        baseline=baseline,
        current=current,
        verify=verify,
        settings=settings,
        scans=scans,
        trades=[],
    )
    schedule_items = [i for i in result.items if i.category == "schedule"]
    drift_text = " ".join(i.detail for i in schedule_items if "预期" in i.detail)
    assert "S3" in drift_text or not drift_text
    assert "S2 预期" not in drift_text


def test_generate_mss_and_schedule_improvements():
    settings = load_settings()
    baseline = {"mss_range": [40, 52], "mss_final": 48, "price": 100}
    current = {
        "mss_final": 38,
        "verdict": "观察",
        "mss_breakdown": {"technical": 42},
        "portfolio": {"cash_ratio": 0.35, "holdings": [{"code": "688008", "change_pct": -6}]},
        "watchlist": [{"code": "603986", "change_pct": -6}, {"code": "000725", "change_pct": -7}],
    }
    verify = {
        "mss_within_prediction": False,
        "mss_delta": -10,
        "verdict_current": "观察",
        "recommendations": ["维持观望"],
    }
    scans = [
        {"scan_id": "S1", "as_of": "2026-07-08T22:00:00+00:00", "mss_final": 47},
        {"scan_id": "S2", "as_of": "2026-07-08T23:00:00+00:00", "mss_final": 48, "source": "morning"},
        {"scan_id": "S3", "as_of": "2026-07-08T00:00:00+00:00", "mss_final": 46},
    ]
    curve = {"trend": "震荡走弱", "prediction_hit": False, "deviation": "尾盘偏低"}

    result = generate_close_improvements(
        baseline=baseline,
        current=current,
        verify=verify,
        settings=settings,
        curve=curve,
        scans=scans,
        trades=[],
    )
    assert result.items
    cats = {i.category for i in result.items}
    assert "mss" in cats
    assert "schedule" in cats
    assert "portfolio" in cats
    assert "watchlist" in cats
    md = render_improvements_markdown(result)
    assert "复盘改进意见" in md
    assert "MSS" in md

# -*- coding: utf-8
"""Tests for weekly forecast accuracy tracking."""

from datetime import date

from agent_reach.daily_run.forecast_tracking import (
    build_daily_structured_checks,
    build_kronos_divergence_day_checks,
    build_monthly_accuracy_summary,
    build_structured_week_review,
    enrich_week_verification_metrics,
    record_week_verification_to_tracking,
    render_daily_structured_checks_markdown,
    render_structured_week_verify_markdown,
)


def _forecast_fixture():
    return {
        "week_start": "2026-08-24",
        "week_end": "2026-08-28",
        "trading_days": ["2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28", "2026-08-29"],
        "structured_predictions": {
            "market": {
                "index_name": "沪深300",
                "change_pct_low": 0.5,
                "change_pct_high": 1.5,
                "change_pct_mid": 1.0,
            },
            "symbols": [
                {
                    "code": "300308",
                    "name": "中际旭创",
                    "base_price": 115.0,
                    "price_low": 110.0,
                    "price_high": 125.0,
                    "price_mid": 118.0,
                    "change_pct_low": -2.0,
                    "change_pct_high": 5.0,
                    "change_pct_mid": 1.5,
                }
            ],
        },
        "actuals": {
            "2026-08-25": {
                "symbols": {"300308": {"change_pct": 0.5, "hit": True}},
            },
            "2026-08-26": {
                "symbols": {"300308": {"change_pct": -0.3, "hit": True}},
            },
        },
        "operation_matrix": {
            "master_rows": [
                {
                    "code": "300308",
                    "name": "中际旭创",
                    "current_weight_pct": 15,
                    "operation": "加仓",
                    "target_weight": "15%→20%",
                }
            ]
        },
    }


def test_build_daily_structured_checks_format():
    forecast = _forecast_fixture()
    snapshot = {
        "portfolio": {
            "holdings": [{"code": "300308", "name": "中际旭创", "price": 118.0, "change_pct": 0.2}]
        }
    }
    checks = build_daily_structured_checks(
        forecast,
        snapshot,
        trading_date=date(2026, 8, 26),
    )
    assert checks
    sym = next(c for c in checks if c.get("kind") == "symbol")
    assert "周预测验证" in sym["text"]
    assert "110-125" in sym["text"]
    assert "118" in sym["text"]
    assert "在区间内" in sym["text"]
    md = render_daily_structured_checks_markdown(checks)
    assert "周预测关键判断" in md


def test_enrich_week_verification_metrics():
    forecast = _forecast_fixture()
    forecast["actuals"]["2026-08-27"] = {"symbols": {"300308": {"change_pct": 1.0}}}
    forecast["actuals"]["2026-08-28"] = {"symbols": {"300308": {"change_pct": 0.5}}}
    base = {
        "week_start": "2026-08-24",
        "week_end": "2026-08-28",
        "rows": [
            {
                "prediction": "中际旭创 110-125元",
                "actual": "118元",
                "verify": "✅ 命中区间",
                "deviation": "+0.5%",
                "hit": True,
            }
        ],
        "hits": 1,
        "total": 1,
        "accuracy_pct": 100.0,
        "avg_deviation_pct": 0.5,
    }
    enriched = enrich_week_verification_metrics(base, forecast, settings={})
    metrics = enriched.get("metrics") or {}
    assert metrics.get("interval_hit_rate_pct") == 100.0
    assert metrics.get("direction_accuracy_pct") is not None
    assert "operation_returns" in metrics


def test_render_structured_week_verify_markdown():
    review = enrich_week_verification_metrics(
        {
            "week_start": "2026-08-24",
            "week_end": "2026-08-28",
            "rows": [
                {
                    "prediction": "中际旭创 110-125元",
                    "actual": "118元",
                    "verify": "✅ 命中区间",
                    "deviation": "+0.5%",
                    "hit": True,
                }
            ],
            "hits": 1,
            "total": 1,
            "accuracy_pct": 100.0,
            "avg_deviation_pct": 0.5,
        },
        _forecast_fixture(),
        settings={},
    )
    lines = render_structured_week_verify_markdown(review)
    text = "\n".join(lines)
    assert "区间命中率" in text
    assert "方向准确率" in text
    assert "平均偏差" in text


def test_record_week_verification_to_tracking(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.forecast_tracking.tracking_path",
        lambda: tmp_path / "tracking.json",
    )
    forecast = _forecast_fixture()
    review = enrich_week_verification_metrics(
        {
            "week_start": "2026-08-24",
            "week_end": "2026-08-28",
            "rows": [
                {
                    "prediction": "中际旭创 110-125元",
                    "actual": "130元",
                    "verify": "❌ 未命中",
                    "deviation": "+5%",
                    "hit": False,
                    "reason": "突破上沿",
                }
            ],
            "hits": 0,
            "total": 1,
            "accuracy_pct": 0.0,
            "avg_deviation_pct": 5.0,
        },
        forecast,
        settings={},
    )
    store = record_week_verification_to_tracking(review, forecast, settings={})
    assert store.get("error_cases")
    summary = build_monthly_accuracy_summary(as_of=date(2026, 8, 28), settings={})
    assert summary.get("rows") or summary.get("recent_error_cases")


def test_build_structured_week_review_from_forecast():
    forecast = _forecast_fixture()
    review = build_structured_week_review(forecast, settings={})
    assert review.get("rows") or review.get("metrics")


def test_build_kronos_divergence_day_checks():
    forecast = {
        "trading_days": ["2026-09-15"],
        "symbols": {
            "688008": {
                "name": "澜起科技",
                "kronos_divergence_days": ["2026-09-15"],
                "days": {
                    "2026-09-15": {
                        "kronos_change_pct": -0.02,
                    }
                },
            },
            "002583": {
                "name": "海能达",
                "kronos_divergence_days": ["2026-09-15"],
                "days": {
                    "2026-09-15": {
                        "kronos_change_pct": -0.47,
                    }
                },
            },
        },
    }
    snapshot = {
        "portfolio": {
            "holdings": [
                {"code": "688008", "change_pct": 1.72},
                {"code": "002583", "change_pct": -1.45},
            ]
        }
    }
    checks = build_kronos_divergence_day_checks(
        forecast,
        snapshot,
        trading_date=date(2026, 9, 15),
    )
    assert len(checks) == 2
    by_code = {c["code"]: c for c in checks}
    assert by_code["688008"]["hit"] is False
    assert by_code["002583"]["hit"] is True
    md = render_daily_structured_checks_markdown(checks)
    assert "Kronos 分歧日验证" in md

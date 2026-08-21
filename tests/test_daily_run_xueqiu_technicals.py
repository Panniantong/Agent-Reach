# -*- coding: utf-8
"""Tests for Xueqiu K-line technicals fallback."""

from agent_reach.daily_run.xueqiu_technicals import _parse_kline_technicals


def test_parse_kline_technicals_extracts_ma20_and_volume_ratio():
    data = {
        "data": {
            "column": [
                "timestamp",
                "volume",
                "open",
                "high",
                "low",
                "close",
                "chg",
                "percent",
                "turnoverrate",
                "amount",
                "volume_post",
                "amount_post",
                "ma5",
                "ma10",
                "ma20",
                "ma30",
            ],
            "item": [
                [1, 100, 5.0, 5.1, 4.9, 5.0, 0, 0, 1, 1000, 0, 0, 5.0, 5.0, 5.0, 5.0],
                [2, 120, 5.1, 5.2, 5.0, 5.1, 0, 0, 1, 1000, 0, 0, 5.05, 5.02, 5.01, 5.0],
                [3, 110, 5.1, 5.15, 5.05, 5.08, 0, 0, 1, 1000, 0, 0, 5.06, 5.03, 5.02, 5.01],
                [4, 130, 5.08, 5.2, 5.0, 5.12, 0, 0, 1, 1000, 0, 0, 5.08, 5.04, 5.03, 5.02],
                [5, 140, 5.12, 5.25, 5.1, 5.2, 0, 0, 1, 1000, 0, 0, 5.1, 5.05, 5.04, 5.03],
            ],
        }
    }
    out = _parse_kline_technicals(data, lookback=5)
    assert out["ma20"] == 5.04
    assert out["ma5"] == 5.1
    assert out["volume_ratio"] == 1.17
    assert out["technicals_source"] == "xueqiu"

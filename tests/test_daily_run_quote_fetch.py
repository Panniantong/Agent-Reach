# -*- coding: utf-8
"""Tests for multi-source quote fetch helpers."""

from agent_reach.daily_run.quote_fetch import (
    _parse_eastmoney_change_pct,
    normalize_code,
)


class TestEastmoneyChangePct:
    def test_f170_scaled_by_100(self):
        data = {"f43": 581, "f60": 586, "f169": -5, "f170": -85}
        assert _parse_eastmoney_change_pct(data) == -0.85

    def test_fallback_from_price_and_prev_close(self):
        data = {"f43": 21191, "f60": 21022}
        assert _parse_eastmoney_change_pct(data) == 0.8

    def test_zero_change(self):
        data = {"f170": 0, "f43": 1000, "f60": 1000}
        assert _parse_eastmoney_change_pct(data) == 0.0


class TestNormalizeCode:
    def test_pad_digits(self):
        assert normalize_code("725") == "000725"

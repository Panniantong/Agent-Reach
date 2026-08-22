# -*- coding: utf-8
"""Tests for multi-source quote fetch helpers."""

from agent_reach.daily_run.quote_fetch import (
    _merge_valuation_fields,
    _parse_eastmoney_change_pct,
    _parse_eastmoney_market_cap,
    _parse_eastmoney_pe_ttm,
    _parse_eastmoney_turnover,
    _parse_eastmoney_valuation,
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


class TestEastmoneyValuation:
    def test_parse_pe_turnover_market_cap(self):
        data = {
            "f162": 3050,
            "f168": 345,
            "f116": 2260000000000,
        }
        assert _parse_eastmoney_pe_ttm(data) == 30.5
        assert _parse_eastmoney_turnover(data) == 3.45
        assert _parse_eastmoney_market_cap(data) == 2260000000000
        parsed = _parse_eastmoney_valuation(data)
        assert parsed["pe_ttm"] == 30.5
        assert parsed["turnover_rate"] == 3.45
        assert parsed["market_capital"] == 2260000000000

    def test_merge_valuation_fields_backfills_missing(self):
        merged = _merge_valuation_fields(
            {"code": "688008", "price": 58.1, "source": "eastmoney"},
            {"pe_ttm": 35.2, "turnover_rate": 2.1},
        )
        assert merged["pe_ttm"] == 35.2
        assert merged["price"] == 58.1

# -*- coding: utf-8
"""Tests for PE / turnover valuation metrics and expert card display."""

from agent_reach.daily_run.team import render_merged_experts_markdown, render_team_markdown
from agent_reach.daily_run.valuation_metrics import (
    format_market_cap,
    format_pe_ttm,
    format_turnover_rate,
    format_valuation_line,
    normalize_market_cap_yuan,
    normalize_turnover_pct,
)


class TestValuationMetrics:
    def test_format_pe_and_turnover(self):
        assert format_pe_ttm(30.5) == "30.5"
        assert format_pe_ttm(-1) is None
        assert format_turnover_rate(3.45) == "3.45%"
        assert normalize_turnover_pct(0.098) == 9.8
        assert format_turnover_rate(0.098) == "9.80%"

    def test_format_valuation_line(self):
        line = format_valuation_line(
            {"name": "澜起科技", "pe_ttm": 42.3, "turnover_rate": 2.15}
        )
        assert "估值快照" in line
        assert "PE(TTM) **42.3**" in line
        assert "换手率 **2.15%**" in line

    def test_format_market_cap(self):
        assert normalize_market_cap_yuan(2260) == 2260 * 1e8
        assert format_market_cap(2260000000000) == "2.26万亿"
        assert format_market_cap(85000000000) == "850亿"
        line = format_valuation_line(
            {"name": "中芯国际", "market_capital": 2260000000000, "pe_ttm": 55.0}
        )
        assert "市值 **2.26万亿**" in line


class TestExpertCardValuation:
    def test_render_team_markdown_includes_valuation(self):
        md = render_team_markdown(
            {
                "name": "澜起科技",
                "code": "688008",
                "pe_ttm": 35.2,
                "turnover_rate": 1.8,
                "team_review": {
                    "mode": "full_parallel",
                    "consensus_score": 58,
                    "consensus_label": "观察",
                    "expert_results": [
                        {
                            "name": "fundamental",
                            "score": 60,
                            "summary": "PE(TTM) 35.2",
                            "success": True,
                        }
                    ],
                },
                "expert_results": [
                    {
                        "name": "fundamental",
                        "score": 60,
                        "summary": "PE(TTM) 35.2",
                        "success": True,
                    }
                ],
            }
        )
        assert "估值快照" in md
        assert "PE(TTM)" in md
        assert "换手率" in md
        assert "基本面大师" in md

    def test_render_merged_experts_markdown_includes_valuation(self):
        md = render_merged_experts_markdown(
            [
                (
                    "澜起科技",
                    "688008",
                    {
                        "pe_ttm": 35.2,
                        "turnover_rate": 1.8,
                        "team_consensus_score": 58,
                        "team_consensus_label": "观察",
                        "expert_results": [
                            {"name": "fundamental", "score": 60, "summary": "ok", "success": True}
                        ],
                    },
                ),
                (
                    "兆易创新",
                    "603986",
                    {
                        "pe_ttm": 48.0,
                        "turnover_rate": 2.5,
                        "team_consensus_score": 55,
                        "team_consensus_label": "观察",
                        "expert_results": [
                            {"name": "fundamental", "score": 58, "summary": "ok", "success": True}
                        ],
                    },
                ),
            ]
        )
        assert "估值快照" in md
        assert "澜起科技" in md
        assert "兆易创新" in md

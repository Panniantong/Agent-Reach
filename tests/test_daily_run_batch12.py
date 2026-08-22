# -*- coding: utf-8
"""Tests for Batch 12: supervisor counter LLM + macro breadth fallback."""

from unittest.mock import patch

from agent_reach.daily_run.market_review import (
    _attach_macro_collector_fallback,
    collect_market_review,
    render_market_review_markdown,
)
from agent_reach.daily_run.supervisor_counter_llm import enrich_counter_thesis_llm
from agent_reach.daily_run.team import _build_counter_thesis, supervisor_review


def _bullish_results():
    return [
        {"name": "technical", "score": 62, "summary": "突破", "success": True},
        {"name": "fundamental", "score": 58, "summary": "业绩稳", "success": True},
        {"name": "risk", "score": 52, "summary": "可控", "success": True},
        {"name": "macro", "score": 55, "summary": "偏暖", "success": True},
    ]


@patch("agent_reach.daily_run.settings.effective_settings", side_effect=lambda settings: settings)
def test_supervisor_counter_llm_enrichment(_mock_eff):
    snapshot = {
        "expert_results": _bullish_results(),
        "mss_breakdown": {"global": 50},
        "sources": {"quote": {"summary": "上证 +0.8%"}},
    }
    settings = {
        "team": {
            "counter_thesis_downgrade": True,
            "counter_thesis_llm": {"enabled": True, "provider": "deepseek"},
        },
        "thresholds": {"macro_veto": 40, "aggressive_entry": 50},
    }
    llm_payload = {
        "counter_factors": ["若政策预期落空，热点或快速退潮"],
        "counter_thesis": "增量叙事尚未被成交确认",
        "recommend_downgrade": True,
    }
    with patch(
        "agent_reach.daily_run.llm_chat.resolve_chat_provider",
        return_value="deepseek",
    ), patch(
        "agent_reach.daily_run.llm_chat.chat_json",
        return_value=llm_payload,
    ):
        review = supervisor_review(snapshot, settings)

    assert review.consensus_label == "可做"
    assert any("政策预期" in f or "退潮" in f for f in review.counter_factors)
    assert "增量叙事" in review.counter_thesis
    assert review.counter_downgrade is True
    assert snapshot.get("team_counter_llm", {}).get("planner") == "llm"


@patch("agent_reach.daily_run.settings.effective_settings", side_effect=lambda settings: settings)
def test_build_counter_thesis_without_llm(_mock_eff):
    by_name = {"technical": 62, "risk": 52, "macro": 55}
    markdown, factors, downgrade = _build_counter_thesis(
        {"expert_results": _bullish_results(), "mss_breakdown": {"global": 50}},
        label="可做",
        conflicts=[],
        by_name=by_name,
        macro_veto=40,
        settings={"team": {"counter_thesis_llm": {"enabled": False}}},
    )
    assert factors
    assert markdown.startswith("反面检验：")
    assert downgrade is False


def test_enrich_counter_thesis_llm_no_provider():
    with patch(
        "agent_reach.daily_run.llm_chat.resolve_chat_provider",
        return_value=None,
    ), patch(
        "agent_reach.daily_run.llm_chat.chat_json",
        return_value=None,
    ):
        factors, thesis, downgrade, meta = enrich_counter_thesis_llm(
            {},
            base_factors=["base risk"],
            conflicts=[],
            by_name={},
            label="可做",
            settings={"team": {"counter_thesis_llm": {"enabled": True}}},
        )
    assert factors == ["base risk"]
    assert meta.get("reason") == "no_llm_provider"
    assert downgrade is False


def test_attach_macro_collector_fallback_enriches_emotion():
    payload = {
        "emotion": {
            "breadth_degraded": True,
            "reasons": ["全 A 宽度不可用，仅指数+北向估算"],
            "warnings": [],
        },
        "indices": {"sh000001": {"change_pct": 0.4}},
        "error": "市场宽度与指数均不可用",
        "warnings": [],
    }
    macro = {
        "macro_summary": "大盘 +0.40%；北向 +12.00亿",
        "sources": {
            "quote": {"summary": "上证 +0.40%", "backend": "macro_collector"},
            "flow": {"summary": "北向资金净流入 12.00 亿", "backend": "macro_collector"},
        },
        "macro_signals": {"index_change_pct": 0.4, "northbound_flow_yi": 12.0},
    }
    with patch(
        "agent_reach.daily_run.macro_collector.collect_macro_context",
        return_value=macro,
    ):
        out = _attach_macro_collector_fallback(payload, settings={"market_review": {}})

    assert out.get("macro_fallback", {}).get("summary")
    assert out["emotion"].get("macro_fallback") is True
    assert any("macro_collector" in r or "macro ·" in r for r in out["emotion"]["reasons"])
    assert "error" not in out


def test_render_markdown_shows_macro_fallback():
    md = render_market_review_markdown(
        {
            "date": "2026-08-20",
            "indices": {"sh000001": {"name": "上证指数", "change_pct": 0.4, "price": 3000}},
            "emotion": {
                "score": 1,
                "rating": "中",
                "position": "5成",
                "breadth_degraded": True,
                "macro_fallback": True,
                "reasons": ["降级"],
                "northbound_net_yi": 12,
            },
            "macro_fallback": {
                "summary": "大盘 +0.40%；北向 +12.00亿",
                "sources": {"flow": {"summary": "北向资金净流入 12.00 亿"}},
            },
            "sector_analysis": {"mainline_type": "多题材轮动", "reasoning": "样本少"},
            "lhb_analysis": {},
            "comparison": {},
        }
    )
    assert "macro_collector 降级摘要" in md
    assert "北向资金净流入" in md


@patch("agent_reach.daily_run.market_review._attach_macro_collector_fallback", side_effect=lambda p, **_: p)
@patch("agent_reach.daily_run.market_review._try_limit_pool_enrichment")
@patch("agent_reach.daily_run.market_review._try_xueqiu_breadth_emotion")
@patch("agent_reach.daily_run.eastmoney_market.fetch_all_stocks")
@patch("agent_reach.daily_run.akshare_adapter.fetch_all_a_spot_stocks")
@patch("agent_reach.daily_run.eastmoney_market.fetch_indices")
@patch("agent_reach.daily_run.eastmoney_market.fetch_north_flow_resilient")
@patch("agent_reach.daily_run.eastmoney_market.fetch_lhb")
def test_collect_calls_macro_fallback_when_degraded(
    mock_lhb,
    mock_north,
    mock_indices,
    mock_ak,
    mock_em_stocks,
    mock_xq,
    mock_limit,
    _mock_attach,
):
    mock_em_stocks.side_effect = RuntimeError("clist blocked")
    mock_ak.side_effect = RuntimeError("akshare blocked")
    mock_indices.return_value = {"sh000001": {"change_pct": 0.2, "name": "上证指数"}}
    mock_north.return_value = ({"net_yi": 5.0}, [])
    mock_lhb.return_value = []
    mock_xq.return_value = (None, ["xq fail"], None)
    mock_limit.side_effect = lambda emotion, *args, **kwargs: (emotion, [], [], None)

    with patch(
        "agent_reach.daily_run.market_review._attach_macro_collector_fallback",
        wraps=_attach_macro_collector_fallback,
    ) as attach_mock:
        review = collect_market_review(settings={"market_review": {}}, review_date="2026-08-20")

    attach_mock.assert_called_once()
    assert review["emotion"].get("breadth_degraded") is True

# -*- coding: utf-8
"""Tests for Eastmoney intent routing."""

from unittest.mock import patch

from agent_reach.daily_run.eastmoney_intent import (
    detect_eastmoney_intent,
    eastmoney_intent_enabled,
    format_eastmoney_intent_summary,
    route_eastmoney_intent,
)


def test_detect_eastmoney_intent():
    assert detect_eastmoney_intent("688008 澜起科技") == "query"
    assert detect_eastmoney_intent("688008") == "query"
    assert detect_eastmoney_intent("涨幅榜 半导体") == "stock-screen"
    assert detect_eastmoney_intent("澜起科技 新闻") == "news-search"
    assert detect_eastmoney_intent("存储芯片 热点") == "news-search"


def test_eastmoney_intent_enabled_respects_plugins():
    assert eastmoney_intent_enabled({"plugins": {"eastmoney_intent_enabled": True}})
    assert not eastmoney_intent_enabled({"plugins": {"eastmoney_intent_enabled": False}})
    assert not eastmoney_intent_enabled({"plugins": {"channel_enrich": False}})


def test_format_eastmoney_intent_summary_query():
    text = format_eastmoney_intent_summary(
        {
            "intent": "query",
            "items": [
                {
                    "code": "688008",
                    "name": "澜起科技",
                    "change_pct": 1.2,
                    "pe_ttm": 30.5,
                }
            ],
        }
    )
    assert text.startswith("东财行情：澜起科技(688008)")
    assert "PE 30.5" in text


def test_format_eastmoney_intent_summary_screen():
    text = format_eastmoney_intent_summary(
        {
            "intent": "stock-screen",
            "items": [
                {"name": "兆易创新", "change_pct": 5.1},
                {"name": "龙芯中科", "change_pct": 4.2},
            ],
        }
    )
    assert text.startswith("东财选股：")
    assert "兆易创新" in text


@patch(
    "agent_reach.daily_run.eastmoney_intent.query_eastmoney_stock",
    return_value={"code": "688008", "name": "澜起科技", "change_pct": 0.8},
)
def test_route_eastmoney_intent_query(mock_query):
    result = route_eastmoney_intent(
        "688008",
        settings={"plugins": {"eastmoney_intent_enabled": True}, "intent": {"enabled": False}},
    )
    assert result["intent"] == "query"
    assert result["items"][0]["name"] == "澜起科技"
    mock_query.assert_called_once()


@patch(
    "agent_reach.daily_run.eastmoney_intent.search_eastmoney_news",
    return_value=[{"title": "存储芯片景气回升", "source": "东财"}],
)
def test_route_eastmoney_intent_news(mock_news):
    result = route_eastmoney_intent(
        "存储芯片 资讯",
        settings={
            "plugins": {"eastmoney_intent_enabled": True, "eastmoney_news_limit": 3},
            "intent": {"enabled": False},
        },
    )
    assert result["intent"] == "news-search"
    assert result["items"][0]["title"] == "存储芯片景气回升"
    mock_news.assert_called_once()


def test_route_eastmoney_intent_disabled():
    result = route_eastmoney_intent(
        "688008",
        settings={"plugins": {"eastmoney_intent_enabled": False}},
    )
    assert result.get("skipped") is True
    assert result["items"] == []


@patch(
    "agent_reach.daily_run.eastmoney_intent.route_eastmoney_intent",
    return_value={
        "intent": "news-search",
        "items": [{"title": "半导体景气", "source": "东财"}],
    },
)
def test_attach_eastmoney_macro_context(mock_route):
    from agent_reach.daily_run.eastmoney_intent import attach_eastmoney_macro_context

    signals: dict = {"hot_topics_matched": [{"title": "半导体"}]}
    sources: dict = {}
    attach_eastmoney_macro_context(
        signals,
        sources,
        {"holdings": [{"code": "688008", "name": "澜起科技"}]},
        settings={"plugins": {"eastmoney_intent_enabled": True, "eastmoney_macro_enabled": True}},
    )
    assert signals.get("eastmoney_intent")
    assert sources["eastmoney"]["summary"].startswith("东财资讯：")
    mock_route.assert_called_once()


def test_render_eastmoney_macro_markdown_from_review():
    from agent_reach.daily_run.eastmoney_intent import render_eastmoney_macro_markdown

    md = render_eastmoney_macro_markdown(
        market_review={"eastmoney_summary": "东财资讯：存储芯片 | 景气回升"}
    )
    assert "东财路由" in md
    assert "存储芯片" in md

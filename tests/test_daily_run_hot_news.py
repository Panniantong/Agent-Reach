# -*- coding: utf-8
"""Tests for 60s hot-news collector integration."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from agent_reach.daily_run.hot_news_collector import (
    HotNewsResult,
    collect_hot_news,
    portfolio_keywords,
    render_hot_news_text,
    _normalize_60s_daily,
    _normalize_platform,
    _matches_keywords,
)
from agent_reach.daily_run.settings import load_settings


class TestPortfolioKeywords:
    def test_from_holdings_and_extra(self):
        pf = {
            "holdings": [{"name": "澜起科技", "code": "688008"}],
            "watchlist": [{"name": "海能达"}],
        }
        settings = {"hot_news": {"extra_keywords": ["芯片"]}}
        keys = portfolio_keywords(pf, settings)
        assert "澜起科技" in keys
        assert "688008" in keys
        assert "海能达"[:4] in keys or "海能" in keys
        assert "芯片" in keys


class TestNormalize:
    def test_normalize_60s_daily(self):
        raw = {
            "date": "2026-07-22",
            "tip": "保持耐心",
            "news": ["头条一", {"title": "头条二", "link": "https://example.com"}],
        }
        items = _normalize_60s_daily(raw, fetched_at="2026-07-22T00:00:00Z", limit=10)
        assert len(items) == 2
        assert items[0]["title"] == "头条一"
        assert items[0]["platform"] == "60s"
        assert items[1]["link"] == "https://example.com"

    def test_normalize_list_platform(self):
        raw = [{"title": "热搜A", "hot_value": 999}, {"word": "热搜B", "score": 100}]
        items = _normalize_platform("weibo", raw, limit=5)
        assert len(items) == 2
        assert items[0]["platform"] == "weibo"
        assert items[0]["hot_value"] == 999


class TestRenderAndMatch:
    def test_matches_keywords(self):
        assert _matches_keywords("存储芯片大涨", ["芯片"])
        assert not _matches_keywords("无关新闻", ["芯片"])

    def test_render_hot_news_text(self):
        result = HotNewsResult(
            daily_headlines=["要闻1", "要闻2"],
            daily_date="2026-07-22",
            daily_tip="微语",
            matched=[{"platform": "weibo", "title": "芯片板块", "hot_value": 100}],
        )
        text = render_hot_news_text(result)
        assert "60s 今日要闻" in text
        assert "芯片板块" in text
        assert "微语" in text


class TestCollectHotNews:
    @patch("agent_reach.daily_run.hot_news_collector._resolve_base_url", return_value="https://60s.viki.moe")
    @patch("agent_reach.daily_run.hot_news_collector._fetch_platform_cached")
    def test_collect_merges_platforms(self, mock_fetch, _mock_base):
        def side_effect(base, platform, spec, **kwargs):
            if platform == "60s":
                return {"date": "2026-07-22", "tip": "tip", "news": ["存储行业动态"]}
            if platform == "weibo":
                return [{"title": "芯片热搜", "hot_value": 50}]
            return []

        mock_fetch.side_effect = side_effect
        pf = {"holdings": [{"name": "澜起科技", "code": "688008"}]}
        settings = {
            "hot_news": {
                "enabled": True,
                "platforms": ["60s", "weibo"],
                "match_portfolio_keywords": True,
                "extra_keywords": ["存储", "芯片"],
            }
        }
        result = collect_hot_news(pf, settings=settings)
        assert "60s" in result.platforms_ok
        assert "weibo" in result.platforms_ok
        assert result.daily_headlines == ["存储行业动态"]
        assert any("芯片" in m.get("title", "") for m in result.matched)
        assert result.text_feed

    def test_disabled_returns_empty(self):
        pf = {"holdings": []}
        result = collect_hot_news(pf, settings={"hot_news": {"enabled": False}})
        assert result.items == []
        assert result.text_feed == ""


class TestMacroIntegration:
    @patch("agent_reach.daily_run.hot_news_collector.collect_hot_news")
    @patch("agent_reach.daily_run.macro_collector._fetch_xueqiu_hot_stocks", return_value=[])
    @patch("agent_reach.daily_run.macro_collector._fetch_index_change", return_value=0.5)
    @patch("agent_reach.daily_run.macro_collector._fetch_northbound_flow", return_value=12.0)
    @patch("agent_reach.daily_run.macro_collector._fetch_xueqiu_sentiment", return_value=("", [], []))
    def test_macro_includes_hot_news(self, mock_xq, mock_nb, mock_idx, mock_hot_stocks, mock_hot_news):
        from agent_reach.daily_run.macro_collector import collect_macro_context

        mock_hot_news.return_value = HotNewsResult(
            items=[{"title": "芯片", "platform": "weibo"}],
            matched=[{"title": "芯片", "platform": "weibo"}, {"title": "存储", "platform": "60s"}],
            daily_headlines=["宏观要闻"],
            headline_summary="今日要闻：宏观要闻",
            summary="热搜命中：芯片",
            text_feed="feed",
            platforms_ok=["60s", "weibo"],
        )
        pf = {"mss_breakdown": {"fx": 50, "flow": 50, "global": 50, "sentiment": 50}}
        ctx = collect_macro_context(pf, settings=load_settings())
        assert "hot_news" in ctx["sources"]
        assert ctx["macro_signals"]["hot_topic_hits"] == 2
        assert ctx["mss_breakdown"]["sentiment"] > 50

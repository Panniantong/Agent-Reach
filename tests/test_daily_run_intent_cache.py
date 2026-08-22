# -*- coding: utf-8
"""Tests for intent cache + rate limiting."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_reach.daily_run.intent_cache import (
    check_rate_limit,
    clear_intent_cache,
    get_cached_intent,
    intent_cache_dir,
    put_cached_intent,
    record_intent_call,
    run_intent_cached,
)
from agent_reach.daily_run.eastmoney_intent import route_eastmoney_intent


@pytest.fixture(autouse=True)
def _clean_intent_cache(tmp_path, monkeypatch):
    cache_dir = tmp_path / "intent_cache"
    monkeypatch.setattr("agent_reach.daily_run.intent_cache.intent_cache_dir", lambda: cache_dir)
    clear_intent_cache()
    yield
    clear_intent_cache()


def test_put_and_get_cached_intent():
    settings = {"intent": {"enabled": True, "ttl_seconds": 600}}
    payload = {"intent": "news-search", "query": "半导体", "items": [{"title": "景气回升"}]}
    put_cached_intent("news-search", "半导体", payload, settings=settings)
    hit = get_cached_intent("news-search", "半导体", settings=settings)
    assert hit == payload


def _cache_file(intent: str, query: str) -> Path:
    from agent_reach.daily_run.intent_cache import _cache_key, _cache_path

    return _cache_path(_cache_key(intent, query))


def test_get_cached_intent_respects_ttl():
    settings = {"intent": {"enabled": True, "ttl_seconds": 1}}
    payload = {"intent": "news-search", "query": "存储", "items": []}
    put_cached_intent("news-search", "存储", payload, settings=settings)
    cache_file = _cache_file("news-search", "存储")
    assert cache_file.exists()
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    data["ts"] = time.time() - 5
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    assert get_cached_intent("news-search", "存储", settings=settings) is None
    assert get_cached_intent("news-search", "存储", settings=settings, ignore_ttl=True) == payload


def test_run_intent_cached_roundtrip():
    settings = {"intent": {"enabled": True, "ttl_seconds": 600}}
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return {"intent": "demo", "query": "q", "items": [{"v": calls["n"]}]}

    first = run_intent_cached("demo", "q", fetch, settings=settings)
    second = run_intent_cached("demo", "q", fetch, settings=settings)
    assert first["items"][0]["v"] == 1
    assert second.get("from_cache") is True
    assert calls["n"] == 1


def test_rate_limit_blocks_after_max_calls():
    settings = {
        "intent": {
            "enabled": True,
            "rate_limit_enabled": True,
            "rate_limit_max": 2,
            "rate_limit_window_seconds": 300,
        }
    }
    assert check_rate_limit(settings) == (True, None)
    record_intent_call(settings)
    record_intent_call(settings)
    allowed, reason = check_rate_limit(settings)
    assert allowed is False
    assert reason == "rate_limited"


@patch(
    "agent_reach.daily_run.eastmoney_intent.search_eastmoney_news",
    return_value=[{"title": "存储芯片景气回升", "source": "东财"}],
)
def test_route_eastmoney_intent_uses_cache(mock_news):
    settings = {
        "plugins": {"eastmoney_intent_enabled": True},
        "intent": {"enabled": True, "ttl_seconds": 600},
    }
    first = route_eastmoney_intent("存储芯片 资讯", settings=settings)
    second = route_eastmoney_intent("存储芯片 资讯", settings=settings)
    assert first["items"][0]["title"] == "存储芯片景气回升"
    assert second.get("from_cache") is True
    mock_news.assert_called_once()


@patch(
    "agent_reach.daily_run.eastmoney_intent.search_eastmoney_news",
    return_value=[{"title": "热点资讯", "source": "东财"}],
)
def test_route_eastmoney_intent_rate_limit_returns_stale(mock_news):
    settings = {
        "plugins": {"eastmoney_intent_enabled": True},
        "intent": {
            "enabled": True,
            "ttl_seconds": 1,
            "rate_limit_enabled": True,
            "rate_limit_max": 1,
            "rate_limit_window_seconds": 300,
        },
    }
    route_eastmoney_intent("热点 资讯", settings=settings)
    cache_file = _cache_file("news-search", "热点 资讯")
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    data["ts"] = time.time() - 5
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    mock_news.reset_mock()
    second = route_eastmoney_intent("热点 资讯", settings=settings)
    assert second.get("from_cache") is True
    assert second.get("rate_limited") is True
    mock_news.assert_not_called()

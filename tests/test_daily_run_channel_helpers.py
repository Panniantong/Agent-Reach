# -*- coding: utf-8
"""Tests for channel_helpers intent-cached Exa enrich."""

from unittest.mock import patch

from agent_reach.daily_run.channel_helpers import search_exa_snippet


@patch("agent_reach.daily_run.exa_cache.cached_web_search_exa", return_value=([{"title": "存储芯片"}], False))
@patch("agent_reach.daily_run.exa_client.summarize_hits", return_value="存储芯片景气")
def test_search_exa_snippet_uses_intent_cache(mock_summary, mock_exa, tmp_path, monkeypatch):
    cache_dir = tmp_path / "intent_cache"
    monkeypatch.setattr("agent_reach.daily_run.intent_cache.intent_cache_dir", lambda: cache_dir)

    settings = {
        "plugins": {"channel_enrich": True, "max_exa_queries_per_expert": 1},
        "intent": {"enabled": True, "ttl_seconds": 600},
    }
    first = search_exa_snippet("存储芯片 景气", settings)
    second = search_exa_snippet("存储芯片 景气", settings)
    assert first == "存储芯片景气"
    assert second == "存储芯片景气"
    mock_exa.assert_called_once()

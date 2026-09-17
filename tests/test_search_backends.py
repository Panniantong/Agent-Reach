# -*- coding: utf-8 -*-
"""Tests for the Tavily-first web search backend routing."""

from types import SimpleNamespace

import agent_reach.channels.exa_search as search_module
from agent_reach.channels.exa_search import ExaSearchChannel


class _Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_tavily_is_primary_and_usage_check_does_not_search(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return _Response(200, {"key": {"usage": 12, "limit": 1000}})

    monkeypatch.setattr(search_module.requests, "get", fake_get)
    channel = ExaSearchChannel()

    status, message = channel.check({"tavily_api_key": "tvly-test"})

    assert status == "ok"
    assert channel.active_backend == channel.TAVILY_BACKEND
    assert calls == [
        (
            channel._TAVILY_USAGE_URL,
            {
                "headers": {"Authorization": "Bearer tvly-test"},
                "timeout": 10,
            },
        )
    ]
    assert "12/1000" in message


def test_invalid_tavily_key_falls_back_to_configured_exa(monkeypatch):
    monkeypatch.setattr(search_module.requests, "get", lambda *_a, **_k: _Response(401))
    monkeypatch.setattr(search_module.shutil, "which", lambda name: "/usr/bin/mcporter")
    monkeypatch.setattr(
        search_module,
        "inspect_mcporter_config",
        lambda: SimpleNamespace(
            server_names=frozenset({"exa"}),
            imports_unchecked=False,
        ),
    )
    channel = ExaSearchChannel()

    status, message = channel.check({"tavily_api_key": "tvly-invalid"})

    assert status == "warn"
    assert channel.active_backend is None
    assert "Tavily API key 无效" in message
    assert "Exa 已写入 mcporter 配置" in message


def test_search_backend_override_moves_exa_to_the_front():
    channel = ExaSearchChannel()

    ordered = channel.ordered_backends({"exa_search_backend": "exa"})

    assert ordered == [channel.EXA_BACKEND, channel.TAVILY_BACKEND]


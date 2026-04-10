# -*- coding: utf-8 -*-
"""Tests for the external Agent Reach SDK surface."""

from agent_reach.client import AgentReach, AgentReachClient
from agent_reach.config import Config
from agent_reach.results import build_result


class _StubAdapter:
    channel = "github"

    def __init__(self, config=None):
        self.config = config

    def supported_operations(self):
        return ("read",)

    def read(self, value, limit=None):
        return build_result(
            ok=True,
            channel="github",
            operation="read",
            items=[
                {
                    "id": value,
                    "kind": "repository",
                    "title": value,
                    "url": f"https://github.com/{value}",
                    "text": None,
                    "author": "openai",
                    "published_at": None,
                    "source": "github",
                    "extras": {},
                }
            ],
            raw={"value": value, "limit": limit},
            meta={"input": value},
            error=None,
        )


def test_agent_reach_alias_and_namespace_access(tmp_path, monkeypatch):
    config = Config(config_path=tmp_path / "config.yaml")
    monkeypatch.setattr("agent_reach.client.get_adapter", lambda channel, config=None: _StubAdapter(config=config))

    client = AgentReachClient(config=config)
    legacy = AgentReach(config=config)

    assert client.exa_search is client.exa
    assert client.hatena is client.hatena_bookmark
    assert isinstance(legacy, AgentReachClient)
    assert client.searxng._channel == "searxng"
    assert client.crawl4ai._channel == "crawl4ai"
    assert client.hn is client.hacker_news
    assert client.hacker_news._channel == "hacker_news"
    assert client.mcp_registry._channel == "mcp_registry"
    assert client.reddit._channel == "reddit"
    assert client.github.read("openai/openai-python")["ok"] is True


def test_collect_rejects_blank_input(tmp_path):
    client = AgentReachClient(config=Config(config_path=tmp_path / "config.yaml"))

    payload = client.collect("github", "read", "   ")

    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_input"


def test_collect_rejects_invalid_limit(tmp_path):
    client = AgentReachClient(config=Config(config_path=tmp_path / "config.yaml"))

    payload = client.collect("github", "read", "openai/openai-python", limit=0)

    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_input"


def test_collect_reports_unsupported_operation(tmp_path, monkeypatch):
    config = Config(config_path=tmp_path / "config.yaml")
    monkeypatch.setattr("agent_reach.client.get_adapter", lambda channel, config=None: _StubAdapter(config=config))
    client = AgentReachClient(config=config)

    payload = client.collect("github", "search", "openai")

    assert payload["ok"] is False
    assert payload["error"]["code"] == "unsupported_operation"
    assert payload["meta"]["supported_operations"] == ["read"]


def test_collect_reports_unknown_channel(tmp_path, monkeypatch):
    config = Config(config_path=tmp_path / "config.yaml")
    monkeypatch.setattr("agent_reach.client.get_adapter", lambda channel, config=None: None)
    client = AgentReachClient(config=config)

    payload = client.collect("missing", "read", "value")

    assert payload["ok"] is False
    assert payload["error"]["code"] == "unknown_channel"


def test_collect_rejects_crawl_query_for_other_channels(tmp_path, monkeypatch):
    config = Config(config_path=tmp_path / "config.yaml")
    monkeypatch.setattr("agent_reach.client.get_adapter", lambda channel, config=None: _StubAdapter(config=config))
    client = AgentReachClient(config=config)

    payload = client.collect("github", "read", "openai/openai-python", crawl_query="docs")

    assert payload["ok"] is False
    assert payload["error"]["code"] == "unsupported_option"


def test_collect_requires_crawl_query_for_crawl4ai_crawl(tmp_path, monkeypatch):
    class _CrawlStubAdapter:
        def supported_operations(self):
            return ("crawl",)

        def crawl(self, value, limit=None, crawl_query=None):
            return build_result(
                ok=True,
                channel="crawl4ai",
                operation="crawl",
                items=[],
                raw={"crawl_query": crawl_query},
                meta={"input": value, "limit": limit},
                error=None,
            )

    config = Config(config_path=tmp_path / "config.yaml")
    monkeypatch.setattr("agent_reach.client.get_adapter", lambda channel, config=None: _CrawlStubAdapter())
    client = AgentReachClient(config=config)

    missing = client.collect("crawl4ai", "crawl", "https://example.com")
    assert missing["ok"] is False
    assert missing["error"]["code"] == "invalid_input"

    payload = client.collect("crawl4ai", "crawl", "https://example.com", crawl_query="pricing")
    assert payload["ok"] is True
    assert payload["raw"]["crawl_query"] == "pricing"


def test_collect_validates_channel_options_from_contract(tmp_path, monkeypatch):
    class _QiitaStubAdapter:
        def supported_operations(self):
            return ("search",)

        def search(self, value, limit=None, body_mode=None):
            return build_result(
                ok=True,
                channel="qiita",
                operation="search",
                items=[],
                raw={"body_mode": body_mode},
                meta={"input": value, "body_mode": body_mode},
                error=None,
            )

    config = Config(config_path=tmp_path / "config.yaml")
    monkeypatch.setattr("agent_reach.client.get_adapter", lambda channel, config=None: _QiitaStubAdapter())
    client = AgentReachClient(config=config)

    invalid = client.collect("qiita", "search", "python", body_mode="invalid")
    assert invalid["ok"] is False
    assert invalid["error"]["code"] == "invalid_input"
    assert invalid["error"]["details"]["choices"] == ["none", "snippet", "full"]

    payload = client.collect("qiita", "search", "python", body_mode="snippet")
    assert payload["ok"] is True
    assert payload["raw"]["body_mode"] == "snippet"


def test_collect_catches_unexpected_adapter_error(tmp_path, monkeypatch):
    class _BoomAdapter:
        def supported_operations(self):
            return ("read",)

        def read(self, value):
            raise RuntimeError("boom")

    config = Config(config_path=tmp_path / "config.yaml")
    monkeypatch.setattr("agent_reach.client.get_adapter", lambda channel, config=None: _BoomAdapter())
    client = AgentReachClient(config=config)

    payload = client.collect("github", "read", "openai/openai-python")

    assert payload["ok"] is False
    assert payload["error"]["code"] == "internal_error"

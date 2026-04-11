# -*- coding: utf-8 -*-
"""Tests for the narrowed channel registry."""

import urllib.request

from agent_reach.channels import get_all_channels, get_channel
from agent_reach.channels.bluesky import BlueskyChannel
from agent_reach.channels.crawl4ai import Crawl4AIChannel
from agent_reach.channels.exa_search import ExaSearchChannel
from agent_reach.channels.github import GitHubChannel
from agent_reach.channels.hacker_news import HackerNewsChannel
from agent_reach.channels.hatena_bookmark import HatenaBookmarkChannel
from agent_reach.channels.mcp_registry import MCPRegistryChannel
from agent_reach.channels.qiita import QiitaChannel
from agent_reach.channels.reddit import RedditChannel
from agent_reach.channels.searxng import SearXNGChannel
from agent_reach.channels.web import WebChannel


def test_registry_contains_only_supported_channels():
    names = [channel.name for channel in get_all_channels()]
    assert names == [
        "web",
        "exa_search",
        "github",
        "hatena_bookmark",
        "bluesky",
        "qiita",
        "youtube",
        "rss",
        "searxng",
        "crawl4ai",
        "hacker_news",
        "mcp_registry",
        "reddit",
        "twitter",
    ]


def test_get_channel_by_name():
    channel = get_channel("github")
    assert channel is not None
    assert channel.name == "github"


def test_get_unknown_channel_returns_none():
    assert get_channel("not-exists") is None


def test_web_can_handle_any_url():
    channel = WebChannel()
    assert channel.can_handle("https://example.com")
    assert channel.can_handle("https://qiita.com/example")


def test_web_read_uses_jina_reader(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def read(self):
            return b"# hello"

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    text = WebChannel().read("https://example.com/post")
    assert text == "# hello"
    assert captured["url"] == "https://r.jina.ai/https://example.com/post"


def test_github_warns_when_gh_missing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    monkeypatch.setattr("agent_reach.channels.github.find_command", lambda _cmd: None)
    status, message = GitHubChannel().check()
    assert status == "warn"
    assert "GitHub.cli" in message


def test_github_reports_ok_when_env_token_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("GH_TOKEN", "token-from-env")
    monkeypatch.setattr("agent_reach.channels.github.find_command", lambda _cmd: "C:/gh.exe")
    monkeypatch.setattr("agent_reach.channels.github.Path.home", lambda: tmp_path)

    status, message = GitHubChannel().check()

    assert status == "ok"
    assert "Ready for repo view" in message


def test_exa_search_uses_user_scoped_mcporter_config(monkeypatch, tmp_path):
    captured = {}

    class _Result:
        stdout = "exa\n"
        stderr = ""
        returncode = 0

    def fake_run(command, **_kwargs):
        captured["command"] = command
        return _Result()

    monkeypatch.setattr("agent_reach.channels.exa_search.find_command", lambda _cmd: "C:/mcporter.cmd")
    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    status, message = ExaSearchChannel().check()

    assert status == "ok"
    assert "Exa web search" in message
    assert captured["command"][:4] == [
        "C:/mcporter.cmd",
        "--config",
        str(tmp_path / ".mcporter" / "mcporter.json"),
        "config",
    ]


def test_hatena_bookmark_can_handle_any_http_url():
    channel = HatenaBookmarkChannel()
    assert channel.can_handle("https://example.com")


def test_bluesky_can_handle_bsky_urls():
    channel = BlueskyChannel()
    assert channel.can_handle("https://bsky.app/profile/openai.com/post/3abc")


def test_qiita_can_handle_qiita_urls():
    channel = QiitaChannel()
    assert channel.can_handle("https://qiita.com/Qiita/items/example")


def test_searxng_requires_config(tmp_path):
    from agent_reach.config import Config

    channel = SearXNGChannel()
    status, message = channel.check(Config(config_path=tmp_path / "config.yaml"))
    assert status == "off"
    assert "configure searxng-base-url" in message


def test_crawl4ai_can_handle_http_urls():
    channel = Crawl4AIChannel()
    assert channel.can_handle("https://example.com")
    assert not channel.can_handle("notaurl")


def test_hacker_news_can_handle_hn_urls():
    channel = HackerNewsChannel()
    assert channel.can_handle("https://news.ycombinator.com/item?id=8863")
    assert channel.can_handle("https://hn.algolia.com/?q=python")


def test_mcp_registry_can_handle_registry_urls():
    channel = MCPRegistryChannel()
    assert channel.can_handle("https://registry.modelcontextprotocol.io/v0.1/servers")
    assert not channel.can_handle("https://example.com")


def test_reddit_uses_rdt_cli(monkeypatch):
    channel = RedditChannel()
    monkeypatch.setattr("agent_reach.channels.reddit.find_command", lambda _cmd: None)

    status, message = channel.check()
    assert status == "warn"
    assert "rdt-cli" in message

    monkeypatch.setattr("agent_reach.channels.reddit.find_command", lambda _cmd: "C:/rdt.exe")
    status, message = channel.check()
    assert status == "ok"
    assert "no-auth" in message


def test_channel_contract_exposes_operation_option_schema():
    qiita_contract = QiitaChannel().to_contract()
    assert qiita_contract["operation_contracts"]["search"]["options"][0]["cli_flag"] == "--body-mode"
    assert qiita_contract["probe_coverage"] == "full"

    crawl_contract = Crawl4AIChannel().to_contract()
    assert crawl_contract["operation_contracts"]["crawl"]["options"][0]["name"] == "query"
    assert crawl_contract["probe_coverage"] == "none"

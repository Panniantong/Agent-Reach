# -*- coding: utf-8 -*-
"""Tests for the narrowed channel registry."""

import urllib.request

from agent_reach.channels import get_all_channels, get_channel
from agent_reach.channels.exa_search import ExaSearchChannel
from agent_reach.channels.github import GitHubChannel
from agent_reach.channels.web import WebChannel


def test_registry_contains_only_supported_channels():
    names = [channel.name for channel in get_all_channels()]
    assert names == ["web", "exa_search", "github", "youtube", "rss", "twitter"]


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

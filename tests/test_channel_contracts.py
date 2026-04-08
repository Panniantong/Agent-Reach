# -*- coding: utf-8 -*-
"""Contract tests for the supported channels."""

from agent_reach.channels import get_all_channels
from agent_reach.config import Config


def test_channel_registry_contract():
    channels = get_all_channels()
    assert channels
    names = [channel.name for channel in channels]
    assert len(names) == len(set(names))

    for channel in channels:
        assert isinstance(channel.name, str) and channel.name
        assert isinstance(channel.description, str) and channel.description
        assert isinstance(channel.backends, list)
        assert channel.tier in {0, 1, 2}


def test_channel_check_contract_with_minimal_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    config = Config(config_path=tmp_path / "config.yaml")

    for channel in get_all_channels():
        status, message = channel.check(config)
        assert status in {"ok", "warn", "off", "error"}
        assert isinstance(message, str) and message.strip()


def test_youtube_warns_when_node_only_and_no_config(monkeypatch, tmp_path):
    from agent_reach.channels.youtube import YouTubeChannel

    def fake_which(cmd):
        if cmd == "yt-dlp":
            return "/usr/bin/yt-dlp"
        if cmd == "node":
            return "/usr/bin/node"
        return None

    monkeypatch.setattr("shutil.which", fake_which)
    monkeypatch.setattr(
        "agent_reach.channels.youtube.get_ytdlp_config_path",
        lambda: tmp_path / ".config" / "yt-dlp" / "config",
    )

    status, message = YouTubeChannel().check()
    assert status == "warn"
    assert "--js-runtimes" in message


def test_youtube_warns_with_windows_specific_fix_command(monkeypatch, tmp_path):
    from agent_reach.channels.youtube import YouTubeChannel

    def fake_which(cmd):
        if cmd == "yt-dlp":
            return "C:/yt-dlp.exe"
        if cmd == "node":
            return "C:/node.exe"
        return None

    monkeypatch.setattr("shutil.which", fake_which)
    monkeypatch.setattr("agent_reach.utils.paths.sys.platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))

    status, message = YouTubeChannel().check()
    assert status == "warn"
    assert "Select-String" in message
    assert "--js-runtimes node" in message


def test_youtube_ok_when_deno_installed(monkeypatch):
    from agent_reach.channels.youtube import YouTubeChannel

    def fake_which(cmd):
        if cmd == "yt-dlp":
            return "/usr/bin/yt-dlp"
        if cmd == "deno":
            return "/usr/bin/deno"
        return None

    monkeypatch.setattr("shutil.which", fake_which)

    status, _message = YouTubeChannel().check()
    assert status == "ok"


def test_channel_can_handle_contract():
    samples = {
        "web": "https://example.com",
        "exa_search": "https://example.com",
        "github": "https://github.com/openai/openai-python",
        "youtube": "https://www.youtube.com/watch?v=abc",
        "rss": "https://example.com/feed.xml",
        "twitter": "https://x.com/openai/status/1",
    }

    for channel in get_all_channels():
        assert isinstance(channel.can_handle(samples[channel.name]), bool)

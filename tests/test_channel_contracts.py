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
        contract = channel.to_contract()
        assert isinstance(contract["name"], str) and contract["name"]
        assert isinstance(contract["description"], str) and contract["description"]
        assert isinstance(contract["backends"], list)
        assert contract["tier"] in {0, 1, 2}
        assert contract["auth_kind"] in {"none", "token", "cookie", "runtime"}
        assert contract["entrypoint_kind"] in {"cli", "mcp", "http_reader", "python"}
        assert isinstance(contract["operations"], list)
        assert contract["operations"]
        assert isinstance(contract["required_commands"], list)
        assert isinstance(contract["host_patterns"], list)
        assert isinstance(contract["example_invocations"], list)
        assert isinstance(contract["supports_probe"], bool)
        assert isinstance(contract["probe_operations"], list)
        assert contract["probe_coverage"] in {"none", "full", "partial"}
        assert isinstance(contract["install_hints"], list)
        assert isinstance(contract["operation_contracts"], dict)
        assert set(contract["operation_contracts"]) == set(contract["operations"])
        for operation, details in contract["operation_contracts"].items():
            assert details["name"] == operation
            assert isinstance(details["input_kind"], str) and details["input_kind"]
            assert isinstance(details["accepts_limit"], bool)
            assert isinstance(details["options"], list)
            for option in details["options"]:
                assert isinstance(option["name"], str) and option["name"]
                assert isinstance(option["type"], str) and option["type"]
                assert isinstance(option["required"], bool)
                if "minimum" in option:
                    assert isinstance(option["minimum"], int)


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
        "hatena_bookmark": "https://example.com",
        "bluesky": "https://bsky.app/profile/openai.com/post/3abc",
        "qiita": "https://qiita.com/Qiita/items/example",
        "youtube": "https://www.youtube.com/watch?v=abc",
        "rss": "https://example.com/feed.xml",
        "searxng": "https://example.com",
        "crawl4ai": "https://example.com",
        "hacker_news": "https://news.ycombinator.com/item?id=8863",
        "mcp_registry": "https://registry.modelcontextprotocol.io/v0.1/servers",
        "reddit": "https://www.reddit.com/r/redditdev/comments/example/post/",
        "twitter": "https://x.com/openai/status/1",
    }

    for channel in get_all_channels():
        assert isinstance(channel.can_handle(samples[channel.name]), bool)


def test_specific_operation_contracts_cover_channel_specific_options():
    contracts = {channel.name: channel.to_contract() for channel in get_all_channels()}

    qiita_search = contracts["qiita"]["operation_contracts"]["search"]
    assert qiita_search["input_kind"] == "query"
    assert qiita_search["options"][0]["name"] == "body_mode"
    assert qiita_search["options"][0]["choices"] == ["none", "snippet", "full"]
    assert qiita_search["options"][1]["name"] == "page_size"
    assert qiita_search["options"][1]["minimum"] == 1
    assert qiita_search["options"][2]["name"] == "max_pages"
    assert qiita_search["options"][2]["minimum"] == 1
    assert qiita_search["options"][3]["name"] == "page"
    assert qiita_search["options"][3]["minimum"] == 1

    crawl_contract = contracts["crawl4ai"]["operation_contracts"]["crawl"]
    assert crawl_contract["input_kind"] == "url"
    assert crawl_contract["options"][0]["name"] == "query"
    assert crawl_contract["options"][0]["required"] is True
    assert crawl_contract["options"][0]["sdk_kwarg"] == "crawl_query"

    github_search = contracts["github"]["operation_contracts"]["search"]
    assert [option["name"] for option in github_search["options"]] == ["page_size", "max_pages", "page"]
    assert all(option["minimum"] == 1 for option in github_search["options"])
    bluesky_search = contracts["bluesky"]["operation_contracts"]["search"]
    assert [option["name"] for option in bluesky_search["options"]] == ["page_size", "max_pages", "cursor"]
    assert bluesky_search["options"][0]["minimum"] == 1
    assert bluesky_search["options"][1]["minimum"] == 1
    twitter_search = contracts["twitter"]["operation_contracts"]["search"]
    assert [option["name"] for option in twitter_search["options"]] == ["since", "until"]

    assert contracts["hacker_news"]["operation_contracts"]["top"]["input_kind"] == "list"
    assert contracts["mcp_registry"]["operation_contracts"]["read"]["input_kind"] == "registry_server"
    assert contracts["reddit"]["operation_contracts"]["read"]["input_kind"] == "post"
    assert contracts["twitter"]["probe_operations"] == ["user", "search"]
    assert contracts["twitter"]["probe_coverage"] == "partial"
    assert contracts["youtube"]["probe_operations"] == ["read"]
    assert contracts["youtube"]["probe_coverage"] == "full"

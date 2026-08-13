# -*- coding: utf-8 -*-
"""Tests for URL routing and the `agent-reach route` command."""

import json
from argparse import Namespace

import pytest

from agent_reach import cli
from agent_reach.channels import (
    ALL_CHANNELS,
    Channel,
    get_all_channels,
    get_channel,
    get_channel_for_url,
)


class TestRouting:
    @pytest.mark.parametrize("url,expected", [
        ("https://github.com/Panniantong/Agent-Reach", "github"),
        ("https://x.com/user/status/123", "twitter"),
        ("https://twitter.com/user/status/123", "twitter"),
        ("https://www.youtube.com/watch?v=abc", "youtube"),
        ("https://youtu.be/abc", "youtube"),
        ("https://www.reddit.com/r/LocalLLaMA/comments/abc", "reddit"),
        ("https://redd.it/abc", "reddit"),
        ("https://www.facebook.com/zuck", "facebook"),
        ("https://www.instagram.com/nasa", "instagram"),
        ("https://www.bilibili.com/video/BV1xx", "bilibili"),
        ("https://b23.tv/abc", "bilibili"),
        ("https://www.xiaohongshu.com/explore/abc", "xiaohongshu"),
        ("https://xhslink.com/abc", "xiaohongshu"),
        ("https://www.linkedin.com/in/someone", "linkedin"),
        ("https://www.xiaoyuzhoufm.com/episode/abc", "xiaoyuzhou"),
        ("https://www.v2ex.com/t/123", "v2ex"),
        ("https://xueqiu.com/S/SH601138", "xueqiu"),
        ("https://example.com/feed.xml", "rss"),
        ("https://example.com/article", "web"),
    ])
    def test_url_routes_to_expected_channel(self, url, expected):
        assert get_channel_for_url(url).name == expected

    def test_web_is_the_fallback_not_the_first_match(self):
        # WebChannel.can_handle() is True for everything; a specific channel wins
        # regardless of registry order.
        assert get_channel_for_url("https://github.com/a/b").name == "github"

    @pytest.mark.parametrize("bad", ["", "   ", None, 123])
    def test_empty_or_non_string_url_is_rejected(self, bad):
        with pytest.raises(ValueError):
            get_channel_for_url(bad)

    def test_a_raising_matcher_does_not_break_routing(self, monkeypatch):
        class _Exploding(Channel):
            name = "exploding"
            description = "爆炸渠道"

            def can_handle(self, url):
                raise RuntimeError("boom")

        monkeypatch.setattr(
            "agent_reach.channels.ALL_CHANNELS",
            [_Exploding(), *ALL_CHANNELS],
        )
        assert get_channel_for_url("https://github.com/a/b").name == "github"


class TestChannelMetadata:
    def test_every_channel_declares_a_reference_doc(self):
        for ch in get_all_channels():
            assert ch.reference, f"{ch.name} has no reference doc"

    def test_reference_docs_exist_on_disk(self):
        from pathlib import Path

        import agent_reach

        refs = Path(agent_reach.__file__).parent / "skill" / "references"
        for ch in get_all_channels():
            assert (refs / f"{ch.reference}.md").is_file(), (
                f"{ch.name} points at a missing reference: {ch.reference}.md"
            )

    def test_url_commands_only_name_declared_backends(self):
        # A template keyed by a backend that is not a candidate would silently
        # never be emitted.
        for ch in get_all_channels():
            unknown = set(ch.url_commands) - set(ch.backends)
            assert not unknown, f"{ch.name} has url_commands for {unknown}"

    def test_url_command_templates_carry_the_placeholder(self):
        for ch in get_all_channels():
            for backend, template in ch.url_commands.items():
                assert "{url}" in template, f"{ch.name}/{backend} lacks {{url}}"


class TestCommandsForUrl:
    def test_substitutes_the_url(self):
        commands = get_channel("youtube").commands_for_url("https://youtu.be/abc")
        assert commands
        for _, command in commands:
            assert "https://youtu.be/abc" in command
            assert "{url}" not in command

    def test_follows_backend_order(self):
        commands = get_channel("xiaohongshu").commands_for_url("https://xhslink.com/a")
        assert [backend for backend, _ in commands] == [
            "OpenCLI",
            "xhs-cli (xiaohongshu-cli)",
        ]

    def test_honours_a_backend_override(self, tmp_path):
        from agent_reach.config import Config

        config = Config(config_path=tmp_path / "config.yaml")
        config.set("xiaohongshu_backend", "xhs-cli (xiaohongshu-cli)")

        commands = get_channel("xiaohongshu").commands_for_url(
            "https://xhslink.com/a", config
        )

        assert commands[0][0] == "xhs-cli (xiaohongshu-cli)"

    def test_backends_without_a_url_command_are_skipped(self):
        # bilibili reads by BV id — no backend may claim to take a URL.
        assert get_channel("bilibili").commands_for_url("https://b23.tv/a") == []


class TestRouteCommand:
    def test_text_output(self, capsys):
        cli._cmd_route(Namespace(url="https://youtu.be/abc", json=False))
        out = capsys.readouterr().out
        assert "youtube" in out
        assert "yt-dlp" in out
        assert "https://youtu.be/abc" in out
        assert "video.md" in out

    def test_json_output(self, capsys):
        cli._cmd_route(Namespace(url="https://github.com/a/b", json=True))
        payload = json.loads(capsys.readouterr().out)
        assert payload["channel"] == "github"
        assert payload["backends"] == ["gh CLI"]
        assert payload["commands"][0]["backend"] == "gh CLI"
        assert "https://github.com/a/b" in payload["commands"][0]["command"]

    def test_id_based_channel_explains_itself_instead_of_faking_a_command(self, capsys):
        cli._cmd_route(Namespace(url="https://www.bilibili.com/video/BV1xx", json=False))
        out = capsys.readouterr().out
        assert "不接受整条 URL" in out
        assert "social.md" in out

    def test_opencli_channel_falls_back_to_its_usage_line(self, capsys):
        cli._cmd_route(Namespace(url="https://www.facebook.com/zuck", json=False))
        assert "opencli facebook" in capsys.readouterr().out

    def test_unknown_host_falls_back_to_web(self, capsys):
        cli._cmd_route(Namespace(url="https://example.com/post", json=True))
        payload = json.loads(capsys.readouterr().out)
        assert payload["channel"] == "web"
        assert "r.jina.ai" in payload["commands"][0]["command"]

    def test_empty_url_exits_1(self, capsys):
        with pytest.raises(SystemExit) as exc:
            cli._cmd_route(Namespace(url="   ", json=False))
        assert exc.value.code == 1
        assert capsys.readouterr().err.strip()

    def test_route_never_spawns_a_subprocess(self, monkeypatch, capsys):
        import subprocess

        def explode(*args, **kwargs):
            raise AssertionError("route must stay probe-free")

        monkeypatch.setattr(subprocess, "run", explode)
        monkeypatch.setattr(subprocess, "Popen", explode)

        cli._cmd_route(Namespace(url="https://x.com/u/status/1", json=True))

        assert json.loads(capsys.readouterr().out)["channel"] == "twitter"

    def test_route_writes_nothing_to_disk(self, tmp_path, monkeypatch, capsys):
        from agent_reach.config import Config

        target = tmp_path / "never" / "config.yaml"
        monkeypatch.setattr(Config, "CONFIG_DIR", target.parent)
        monkeypatch.setattr(Config, "CONFIG_FILE", target)

        cli._cmd_route(Namespace(url="https://youtu.be/abc", json=True))

        assert not target.parent.exists()

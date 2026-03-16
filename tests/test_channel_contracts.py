# -*- coding: utf-8 -*-
"""Contract tests for channel adapters."""

from agent_reach.channels import get_all_channels
from agent_reach.config import Config


def test_channel_registry_contract():
    channels = get_all_channels()
    assert channels, "channel registry must not be empty"
    names = [ch.name for ch in channels]
    assert len(names) == len(set(names)), "channel names must be unique"

    for ch in channels:
        assert isinstance(ch.name, str) and ch.name
        assert isinstance(ch.description, str) and ch.description
        assert isinstance(ch.backends, list)
        assert ch.tier in {0, 1, 2}


def test_channel_check_contract_with_minimal_runtime(monkeypatch, tmp_path):
    # Keep contract tests deterministic by simulating "deps mostly absent".
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    config = Config(config_path=tmp_path / "config.yaml")

    for ch in get_all_channels():
        status, message = ch.check(config)
        assert status in {"ok", "warn", "off", "error"}
        assert isinstance(message, str) and message.strip()


def test_youtube_warns_when_node_only_and_no_config(monkeypatch, tmp_path):
    """YouTube should warn when only Node.js is installed but no yt-dlp config exists."""
    from agent_reach.channels.youtube import YouTubeChannel

    def fake_which(cmd):
        if cmd == "yt-dlp":
            return "/usr/bin/yt-dlp"
        if cmd == "node":
            return "/usr/bin/node"
        return None  # deno not installed

    monkeypatch.setattr("shutil.which", fake_which)
    # Point to a non-existent config file
    monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path / ".config/yt-dlp/config"))

    ch = YouTubeChannel()
    status, message = ch.check()
    assert status == "warn"
    assert "--js-runtimes" in message


def test_youtube_ok_when_deno_installed(monkeypatch):
    """YouTube should return ok when Deno is installed (no config needed)."""
    from agent_reach.channels.youtube import YouTubeChannel

    def fake_which(cmd):
        if cmd == "yt-dlp":
            return "/usr/bin/yt-dlp"
        if cmd == "deno":
            return "/usr/bin/deno"
        return None

    monkeypatch.setattr("shutil.which", fake_which)

    ch = YouTubeChannel()
    status, _msg = ch.check()
    assert status == "ok"


def test_douyin_check_does_not_call_with_invalid_url(monkeypatch, tmp_path):
    """Douyin check should use 'mcporter list' instead of calling with a hardcoded URL."""
    import subprocess

    from agent_reach.channels.douyin import DouyinChannel

    calls = []
    original_run = subprocess.run

    def tracking_run(cmd, **kwargs):
        calls.append(cmd)
        # Simulate mcporter config list returning douyin
        if "config" in cmd and "list" in cmd:
            class R:
                stdout = "douyin  http://localhost:18070/mcp"
                returncode = 0
            return R()
        # Simulate mcporter list douyin returning tools
        if "list" in cmd and "douyin" in cmd:
            class R:
                stdout = "parse_douyin_video_info"
                returncode = 0
            return R()
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/mcporter" if cmd == "mcporter" else None)
    monkeypatch.setattr("subprocess.run", tracking_run)

    ch = DouyinChannel()
    status, _msg = ch.check()

    # Should NOT contain any hardcoded douyin.com URL in subprocess calls
    for call in calls:
        call_str = " ".join(call) if isinstance(call, list) else str(call)
        assert "https://www.douyin.com" not in call_str


def test_channel_can_handle_contract():
    url_samples = {
        "github": "https://github.com/panniantong/agent-reach",
        "twitter": "https://x.com/user/status/1",
        "youtube": "https://youtube.com/watch?v=abc",
        "reddit": "https://reddit.com/r/python",
        "bilibili": "https://www.bilibili.com/video/BV1xx411",
        "xiaohongshu": "https://www.xiaohongshu.com/explore/123",
        "douyin": "https://www.douyin.com/video/123",
        "linkedin": "https://www.linkedin.com/in/test",
        "weibo": "https://weibo.com/u/1749127163",
        "rss": "https://example.com/feed.xml",
        "xueqiu": "https://xueqiu.com/S/SH600519",
        "exa_search": "https://example.com",
        "web": "https://example.com",
    }
    for ch in get_all_channels():
        sample = url_samples.get(ch.name, "https://example.com")
        result = ch.can_handle(sample)
        assert isinstance(result, bool)

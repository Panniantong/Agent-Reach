# -*- coding: utf-8 -*-
"""Contract tests for channel adapters."""

import subprocess

from agent_reach.channels import get_all_channels
from agent_reach.config import Config


def _fake_run_ok(cmd, **kwargs):
    """Pretend any probed CLI executes fine and prints a version."""
    return subprocess.CompletedProcess(cmd, 0, "2026.06.09", "")


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


def test_channel_active_backend_attribute_contract():
    """Every channel exposes active_backend (default None, or str once set)."""
    for ch in get_all_channels():
        assert hasattr(ch, "active_backend")
        # Fresh instances must default to None / str (class attribute on base)
        fresh = type(ch)()
        assert fresh.active_backend is None or isinstance(fresh.active_backend, str)


def test_channel_active_backend_set_by_check(monkeypatch, tmp_path):
    """After check(), active_backend is None or a str — never anything else."""
    monkeypatch.setattr("shutil.which", lambda _cmd: None)

    # Keep the network-based channels (V2EX/Xueqiu/Bilibili API) deterministic.
    import urllib.request
    from urllib.error import URLError

    def _no_net(*_a, **_k):
        raise URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", _no_net)
    import agent_reach.channels.xueqiu as xueqiu_mod
    monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)
    monkeypatch.setattr(xueqiu_mod._opener, "open", _no_net)

    config = Config(config_path=tmp_path / "config.yaml")
    for ch in get_all_channels():
        ch.check(config)
        assert ch.active_backend is None or isinstance(ch.active_backend, str), (
            f"{ch.name}: active_backend must be None or str after check()"
        )


def test_ordered_backends_contract(tmp_path):
    """ordered_backends(config) is a reordering (same multiset) of backends."""
    config = Config(config_path=tmp_path / "config.yaml")
    for ch in get_all_channels():
        ordered = ch.ordered_backends(config)
        assert isinstance(ordered, list)
        assert sorted(ordered) == sorted(ch.backends), (
            f"{ch.name}: ordered_backends must be a permutation of backends"
        )
        # And without any config at all
        ordered_none = ch.ordered_backends(None)
        assert sorted(ordered_none) == sorted(ch.backends)


def test_ordered_backends_override_moves_backend_to_front():
    """Config key <channel>_backend promotes the named backend to front."""
    from agent_reach.channels.twitter import TwitterChannel

    ch = TwitterChannel()
    ordered = ch.ordered_backends({"twitter_backend": "bird"})
    assert ordered[0] == "bird CLI (legacy)"
    assert sorted(ordered) == sorted(ch.backends)

    # Unknown override is ignored — never hides working backends
    ordered_unknown = ch.ordered_backends({"twitter_backend": "no-such-tool"})
    assert ordered_unknown == list(ch.backends)


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
    monkeypatch.setattr("subprocess.run", _fake_run_ok)  # yt-dlp probe really executes now
    # Point to a non-existent config file
    monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path / ".config/yt-dlp/config"))

    ch = YouTubeChannel()
    status, message = ch.check()
    assert status == "warn"
    assert "--js-runtimes" in message
    assert ch.active_backend == "yt-dlp"  # 本体活着，warn 只关乎 JS runtime


def test_youtube_warns_with_windows_specific_fix_command(monkeypatch, tmp_path):
    """Windows guidance should use a PowerShell-style yt-dlp config command."""
    from agent_reach.channels.youtube import YouTubeChannel

    def fake_which(cmd):
        if cmd == "yt-dlp":
            return "C:/yt-dlp.exe"
        if cmd == "node":
            return "C:/node.exe"
        return None

    monkeypatch.setattr("shutil.which", fake_which)
    monkeypatch.setattr("subprocess.run", _fake_run_ok)  # yt-dlp probe really executes now
    monkeypatch.setattr("agent_reach.utils.paths.sys.platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))

    ch = YouTubeChannel()
    status, message = ch.check()
    assert status == "warn"
    assert "Select-String" in message
    assert "--js-runtimes node" in message


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
    monkeypatch.setattr("subprocess.run", _fake_run_ok)  # yt-dlp probe really executes now

    ch = YouTubeChannel()
    status, _msg = ch.check()
    assert status == "ok"
    assert ch.active_backend == "yt-dlp"


def test_channel_can_handle_contract():
    url_samples = {
        "github": "https://github.com/panniantong/agent-reach",
        "twitter": "https://x.com/user/status/1",
        "youtube": "https://youtube.com/watch?v=abc",
        "reddit": "https://reddit.com/r/python",
        "facebook": "https://www.facebook.com/zuck",
        "instagram": "https://www.instagram.com/openai/",
        "bilibili": "https://www.bilibili.com/video/BV1xx411",
        "xiaohongshu": "https://www.xiaohongshu.com/explore/123",
        "linkedin": "https://www.linkedin.com/in/test",
        "rss": "https://example.com/feed.xml",
        "xueqiu": "https://xueqiu.com/S/SH600519",
        "exa_search": "https://example.com",
        "web": "https://example.com",
    }
    for ch in get_all_channels():
        sample = url_samples.get(ch.name, "https://example.com")
        result = ch.can_handle(sample)
        assert isinstance(result, bool)

# -*- coding: utf-8 -*-
"""Tests for the MCP server's search/read routing and security boundaries.

These test the pure command-builder functions — no upstream tools and no
`mcp` package required, per the repo rule that Agent Reach only routes and
calls (never reimplements) upstream tools.
"""

import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

import agent_reach.integrations.mcp_server as mcp_server
from agent_reach.integrations.mcp_server import (
    MAX_OUTPUT_CHARS,
    SEARCH_PLATFORMS,
    _clip,
    _extract_bilibili_bvid,
    _extract_reddit_post_id,
    _trim_youtube_json,
    build_read_command,
    build_search_command,
    detect_platform,
    run_upstream,
)


# ---------- search routing ----------

def test_search_web_routes_to_mcporter_exa():
    cmd, timeout = build_search_command("web", "ai tools", 5)
    assert cmd[0] == "mcporter"
    assert "exa.web_search_exa" in cmd[2]
    assert "numResults: 5" in cmd[2]
    assert timeout == 120


def test_search_web_escapes_quotes():
    cmd, _ = build_search_command("web", 'say "hi"', 3)
    assert '\\"hi\\"' in cmd[2]


def test_search_twitter():
    cmd, _ = build_search_command("twitter", "claude", 10)
    assert cmd == ["twitter", "search", "claude", "-n", "10"]


def test_search_reddit_uses_opencli():
    cmd, _ = build_search_command("reddit", "faceless tiktok", 5)
    assert cmd[:3] == ["opencli", "reddit", "search"]


def test_search_xiaohongshu_uses_opencli():
    cmd, _ = build_search_command("xiaohongshu", "旅行", 5)
    assert cmd[:3] == ["opencli", "xiaohongshu", "search"]


def test_search_bilibili():
    cmd, _ = build_search_command("bilibili", "编程", 7)
    assert cmd[0] == "bili"
    assert "-n" in cmd and "7" in cmd


def test_search_github():
    cmd, _ = build_search_command("github", "mcp server", 5)
    assert cmd[:3] == ["gh", "search", "repos"]


def test_search_youtube_flat_playlist():
    cmd, _ = build_search_command("youtube", "story narration", 4)
    assert cmd[0] == "yt-dlp"
    assert "ytsearch4:story narration" in cmd[-1]


def test_search_limit_clamped():
    cmd, _ = build_search_command("twitter", "q", 999)
    assert "50" in cmd
    cmd, _ = build_search_command("twitter", "q", 0)
    assert "1" in cmd


def test_search_unknown_platform_raises():
    with pytest.raises(ValueError):
        build_search_command("myspace", "q", 5)


def test_all_declared_platforms_build():
    for p in SEARCH_PLATFORMS:
        cmd, timeout = build_search_command(p, "q", 5)
        assert cmd and timeout > 0


# ---------- URL detection / read routing ----------

def test_detect_platform_youtube():
    assert detect_platform("https://www.youtube.com/watch?v=abc") == "youtube"
    assert detect_platform("https://youtu.be/abc") == "youtube"


def test_detect_platform_generic_web():
    assert detect_platform("https://example.com/article") == "web"


def test_read_youtube_routes_to_ytdlp():
    platform, cmd, _ = build_read_command("https://www.youtube.com/watch?v=abc")
    assert platform == "youtube"
    assert cmd[0] == "yt-dlp"


def test_read_generic_falls_back_to_jina():
    platform, cmd, _ = build_read_command("https://example.com/post")
    assert platform == "web"
    assert cmd[0] == "curl"
    assert cmd[-1].startswith("https://r.jina.ai/")


def test_extract_reddit_post_id():
    url = "https://www.reddit.com/r/NewTubers/comments/1abc2d3/some_title/"
    assert _extract_reddit_post_id(url) == "1abc2d3"
    assert _extract_reddit_post_id("https://www.reddit.com/r/NewTubers/") is None


def test_extract_bilibili_bvid():
    assert _extract_bilibili_bvid(
        "https://www.bilibili.com/video/BV1xx411c7mD?p=1") == "BV1xx411c7mD"
    assert _extract_bilibili_bvid("https://www.bilibili.com/") is None


# ---------- output shaping ----------

def test_trim_youtube_json_keeps_key_fields():
    raw = json.dumps({
        "id": "abc", "title": "T", "description": "D", "formats": [1, 2, 3],
        "subtitles": {"en": []}, "automatic_captions": {"en": [], "es": []},
        "view_count": 42,
    })
    out = json.loads(_trim_youtube_json(raw))
    assert out["title"] == "T"
    assert out["view_count"] == 42
    assert out["subtitle_languages"] == ["en"]
    assert "formats" not in out


def test_trim_youtube_json_passes_through_invalid():
    assert _trim_youtube_json("not json") == "not json"


def test_clip_truncates():
    clipped = _clip("x" * (MAX_OUTPUT_CHARS + 100))
    assert len(clipped) < MAX_OUTPUT_CHARS + 60
    assert "truncated" in clipped


# ---------- subprocess wrapper ----------

def test_search_twitter_falls_back_to_opencli(monkeypatch):
    import agent_reach.integrations.mcp_server as m

    calls = []

    def fake_run(cmd, timeout):
        calls.append(cmd)
        if cmd[0] == "twitter":
            return False, "MISSING_TOOL:twitter not installed"
        return True, "opencli result"

    monkeypatch.setattr(m, "run_upstream", fake_run)
    out = m.do_search("query", "twitter", 5)
    assert out == "opencli result"
    assert calls[0][0] == "twitter"
    assert calls[1][:2] == ["opencli", "twitter"]


def test_search_no_fallback_strips_marker(monkeypatch):
    import agent_reach.integrations.mcp_server as m

    monkeypatch.setattr(
        m, "run_upstream",
        lambda cmd, timeout: (False, "MISSING_TOOL:gh gh is not installed."))
    out = m.do_search("q", "github", 5)
    assert not out.startswith("MISSING_TOOL:")
    assert "not installed" in out


def test_read_bilibili_falls_back_to_opencli(monkeypatch):
    import agent_reach.integrations.mcp_server as m

    def fake_run(cmd, timeout):
        if cmd[0] == "bili":
            return False, "MISSING_TOOL:bili not installed"
        return True, "opencli video"

    monkeypatch.setattr(m, "run_upstream", fake_run)
    out = m.do_read("https://www.bilibili.com/video/BV1xx411c7mD")
    assert out == "opencli video"


def test_run_upstream_missing_tool_gives_install_hint():
    ok, out = run_upstream(["definitely-not-a-real-binary-xyz"], timeout=5)
    assert not ok
    assert "agent-reach install" in out


def test_run_upstream_captures_success():
    # sys.executable, not "python": macOS ships no bare `python` on PATH.
    ok, out = run_upstream([sys.executable, "-c", "print('hello')"], timeout=15)
    assert ok
    assert out == "hello"


# ---------- security boundaries (from upstream) ----------

class _FakeServer:
    def __init__(self, name):
        self.name = name
        self.list_tools_handler = None
        self.call_tool_handler = None

    def list_tools(self):
        def register(handler):
            self.list_tools_handler = handler
            return handler

        return register

    def call_tool(self):
        def register(handler):
            self.call_tool_handler = handler
            return handler

        return register


def _install_fake_mcp(monkeypatch):
    monkeypatch.setattr(mcp_server, "HAS_MCP", True)
    monkeypatch.setattr(mcp_server, "Server", _FakeServer, raising=False)
    monkeypatch.setattr(
        mcp_server,
        "Tool",
        lambda **kwargs: SimpleNamespace(**kwargs),
        raising=False,
    )
    monkeypatch.setattr(
        mcp_server,
        "TextContent",
        lambda **kwargs: SimpleNamespace(**kwargs),
        raising=False,
    )


def test_mcp_status_uses_read_only_config(monkeypatch):
    _install_fake_mcp(monkeypatch)
    created_configs = []

    class _RecordingConfig:
        def __init__(self, *, read_only=False):
            self.read_only = read_only
            created_configs.append(self)

    class _AgentReach:
        def __init__(self, config):
            self.config = config

        def doctor_report(self):
            return "ok"

    monkeypatch.setattr(mcp_server, "Config", _RecordingConfig)
    monkeypatch.setattr(mcp_server, "AgentReach", _AgentReach)

    server = mcp_server.create_server()
    result = asyncio.run(server.call_tool_handler("get_status", {}))

    assert len(created_configs) == 1
    assert created_configs[0].read_only is True
    assert result[0].text == "ok"


def test_mcp_status_exception_credentials_are_scrubbed(monkeypatch):
    _install_fake_mcp(monkeypatch)

    class _Config:
        def __init__(self, *, read_only=False):
            self.read_only = read_only

    class _ExplodingAgentReach:
        def __init__(self, config):
            self.config = config

        def doctor_report(self):
            raise RuntimeError(
                "request https://alice:password@example.test/data"
                "?token=top-secret failed"
            )

    monkeypatch.setattr(mcp_server, "Config", _Config)
    monkeypatch.setattr(mcp_server, "AgentReach", _ExplodingAgentReach)

    server = mcp_server.create_server()
    result = asyncio.run(server.call_tool_handler("get_status", {}))
    text = result[0].text

    assert "alice" not in text
    assert "password" not in text
    assert "top-secret" not in text
    assert "https://***@example.test/data?token=***" in text

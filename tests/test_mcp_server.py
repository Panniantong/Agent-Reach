# -*- coding: utf-8 -*-
"""Tests for the MCP server's search/read routing.

These test the pure command-builder functions — no upstream tools and no
`mcp` package required, per the repo rule that Agent Reach only routes and
calls (never reimplements) upstream tools.
"""

import json

import pytest

from agent_reach.integrations.mcp_server import (
    MAX_OUTPUT_CHARS,
    SEARCH_PLATFORMS,
    _clip,
    _extract_bilibili_bvid,
    _extract_instagram_username,
    _extract_reddit_post_id,
    _extract_tiktok_username,
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


def test_search_instagram_uses_opencli():
    cmd, _ = build_search_command("instagram", "street photography", 5)
    assert cmd == ["opencli", "instagram", "search", "street photography",
                   "-f", "yaml"]


def test_instagram_is_a_declared_platform():
    assert "instagram" in SEARCH_PLATFORMS


def test_search_tiktok_uses_opencli_with_limit():
    cmd, _ = build_search_command("tiktok", "film photography", 8)
    assert cmd == ["opencli", "tiktok", "search", "film photography",
                   "--limit", "8", "-f", "yaml"]


def test_tiktok_is_a_declared_platform():
    assert "tiktok" in SEARCH_PLATFORMS


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


def test_detect_platform_instagram():
    assert detect_platform("https://www.instagram.com/clipfeedtv") == "instagram"


def test_read_instagram_profile_routes_to_opencli():
    platform, cmd, _ = build_read_command("https://www.instagram.com/clipfeedtv/")
    assert platform == "instagram"
    assert cmd == ["opencli", "instagram", "profile", "clipfeedtv", "-f", "yaml"]


def test_read_instagram_post_falls_back_to_jina():
    # OpenCLI reads profiles, not permalinks — posts must not be mis-routed.
    platform, cmd, _ = build_read_command("https://www.instagram.com/p/Cabc123/")
    assert platform == "web"
    assert cmd[0] == "curl"


def test_extract_instagram_username():
    assert _extract_instagram_username(
        "https://www.instagram.com/clipfeedtv/") == "clipfeedtv"
    assert _extract_instagram_username(
        "https://instagram.com/clipfeedtv") == "clipfeedtv"
    assert _extract_instagram_username(
        "https://www.instagram.com/p/Cabc123/") is None
    assert _extract_instagram_username(
        "https://www.instagram.com/reel/Cabc123/") is None
    assert _extract_instagram_username("https://www.instagram.com/") is None


def test_detect_platform_tiktok():
    assert detect_platform("https://www.tiktok.com/@someone") == "tiktok"


def test_read_tiktok_profile_routes_to_opencli():
    platform, cmd, _ = build_read_command("https://www.tiktok.com/@someone")
    assert platform == "tiktok"
    assert cmd == ["opencli", "tiktok", "profile", "someone", "-f", "yaml"]


def test_read_tiktok_video_falls_back_to_jina():
    # OpenCLI's tiktok adapter has no single-video read command.
    platform, cmd, _ = build_read_command(
        "https://www.tiktok.com/@someone/video/7123456789")
    assert platform == "web"
    assert cmd[0] == "curl"


def test_extract_tiktok_username():
    assert _extract_tiktok_username(
        "https://www.tiktok.com/@clipfeedtv") == "clipfeedtv"
    assert _extract_tiktok_username(
        "https://www.tiktok.com/@clipfeedtv/") == "clipfeedtv"
    assert _extract_tiktok_username(
        "https://www.tiktok.com/@user/video/7123") is None
    assert _extract_tiktok_username("https://www.tiktok.com/explore") is None
    assert _extract_tiktok_username("https://www.tiktok.com/") is None


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
    ok, out = run_upstream(["python", "-c", "print('hello')"], timeout=15)
    assert ok
    assert out == "hello"

# -*- coding: utf-8 -*-
"""Dedicated tests for the ``youtube`` channel.

YouTube's readiness is layered: yt-dlp must probe alive (missing / broken /
unrunnable are distinct), a JS runtime is mandatory (deno works out of the
box, Node needs an explicit ``--js-runtimes`` config), and transcription
readiness (whisper provider + ffmpeg) is surfaced for ``doctor`` without
gating the backend. These tests stub ``probe_command`` / ``shutil.which``
so every branch runs offline. Follow-up to #331 — extends dedicated
channel coverage after rss (#360), github (#361), web (#363),
reddit (#364), xueqiu (#365) and v2ex (#366).
"""

from unittest.mock import Mock, patch

from agent_reach.probe import ProbeResult
from agent_reach.channels import youtube as yt
from agent_reach.channels.youtube import YouTubeChannel, _has_js_runtime_config


def _which(*present):
    """shutil.which side effect: returns a path for the named tools present."""
    return lambda name: f"/usr/bin/{name}" if name in present else None


# --- can_handle ---

def test_can_handle_matches_youtube_hosts():
    ch = YouTubeChannel()
    for url in [
        "https://www.youtube.com/watch?v=abc",
        "https://youtu.be/abc",
        "https://m.youtube.com/watch?v=abc",
        "https://YOUTUBE.COM/shorts/x",
    ]:
        assert ch.can_handle(url) is True, url
    for url in ["https://example.com", "https://vimeo.com/123", ""]:
        assert ch.can_handle(url) is False, url


# --- _has_js_runtime_config ---

def test_has_js_runtime_config_missing_file_is_false(tmp_path):
    assert _has_js_runtime_config(tmp_path / "nope.conf") is False


def test_has_js_runtime_config_true_when_flag_present(tmp_path):
    cfg = tmp_path / "config"
    cfg.write_text("--js-runtimes deno\n--no-mtime\n", encoding="utf-8")
    assert _has_js_runtime_config(cfg) is True


def test_has_js_runtime_config_false_when_flag_absent(tmp_path):
    cfg = tmp_path / "config"
    cfg.write_text("--no-mtime\n", encoding="utf-8")
    assert _has_js_runtime_config(cfg) is False


def test_has_js_runtime_config_swallows_oserror():
    bad = Mock()
    bad.exists.return_value = True
    with patch.object(yt, "read_utf8_text", side_effect=OSError("denied")):
        assert _has_js_runtime_config(bad) is False


# --- check(): yt-dlp probe states ---

def test_check_off_when_ytdlp_missing():
    ch = YouTubeChannel()
    with patch.object(yt, "probe_command", return_value=ProbeResult("missing")):
        status, message = ch.check()
    assert status == "off"
    assert ch.active_backend is None


def test_check_error_when_ytdlp_broken():
    ch = YouTubeChannel()
    with patch.object(yt, "probe_command", return_value=ProbeResult("broken", hint="relink venv")):
        status, message = ch.check()
    assert status == "error"
    assert "relink venv" in message
    assert ch.active_backend is None


def test_check_error_when_ytdlp_unrunnable():
    ch = YouTubeChannel()
    with patch.object(yt, "probe_command", return_value=ProbeResult("timeout", hint="too slow")):
        status, message = ch.check()
    assert status == "error"
    assert ch.active_backend is None


# --- check(): JS runtime gating (backend stays yt-dlp once the probe is ok) ---

def test_check_warn_when_no_js_runtime_but_backend_active():
    ch = YouTubeChannel()
    with patch.object(yt, "probe_command", return_value=ProbeResult("ok")), \
         patch("shutil.which", side_effect=_which()):  # no deno, no node
        status, message = ch.check()
    assert status == "warn"
    assert "JS runtime" in message
    assert ch.active_backend == "yt-dlp"  # probe was ok → backend attributed


def test_check_warn_when_node_only_and_config_missing_flag():
    ch = YouTubeChannel()
    with patch.object(yt, "probe_command", return_value=ProbeResult("ok")), \
         patch("shutil.which", side_effect=_which("node")), \
         patch.object(yt, "_has_js_runtime_config", return_value=False):
        status, message = ch.check()
    assert status == "warn"
    assert ch.active_backend == "yt-dlp"


def test_check_ok_with_deno():
    ch = YouTubeChannel()
    with patch.object(yt, "probe_command", return_value=ProbeResult("ok")), \
         patch("shutil.which", side_effect=_which("deno")):
        status, message = ch.check()
    assert status == "ok"
    assert message == "可提取视频信息和字幕"
    assert ch.active_backend == "yt-dlp"


# --- check(): transcription readiness surfaced (deno present so JS path is ok) ---

def test_check_ok_reports_transcription_when_provider_and_ffmpeg_present():
    ch = YouTubeChannel()
    cfg = Mock()
    cfg.is_configured = lambda key: key == "groq_whisper"
    with patch.object(yt, "probe_command", return_value=ProbeResult("ok")), \
         patch("shutil.which", side_effect=_which("deno", "ffmpeg")):
        status, message = ch.check(config=cfg)
    assert status == "ok"
    assert "groq" in message
    assert "可转写音频" in message


def test_check_ok_flags_missing_ffmpeg_for_transcription():
    ch = YouTubeChannel()
    cfg = Mock()
    cfg.is_configured = lambda key: key == "openai_whisper"
    with patch.object(yt, "probe_command", return_value=ProbeResult("ok")), \
         patch("shutil.which", side_effect=_which("deno")):  # provider yes, ffmpeg no
        status, message = ch.check(config=cfg)
    assert status == "ok"
    assert "ffmpeg" in message

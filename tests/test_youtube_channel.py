# -*- coding: utf-8 -*-
"""Dedicated tests for the ``youtube`` channel.

YouTube's readiness is layered: yt-dlp must probe alive (missing / broken /
unrunnable are distinct), a JS runtime is mandatory (deno works out of the
box, Node needs an explicit ``--js-runtimes`` config), and transcription
readiness (whisper provider + ffmpeg/ffprobe) is surfaced for ``doctor`` without
gating the backend. These tests stub ``probe_command`` / ``shutil.which``
so every branch runs offline. Follow-up to #331 — extends dedicated
channel coverage after rss (#360), github (#361), web (#363),
reddit (#364), xueqiu (#365) and v2ex (#366).
"""

import json
from pathlib import Path

from agent_reach.channels.youtube import YouTubeChannel


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









# --- check(): yt-dlp probe states ---







# --- check(): JS runtime gating (backend stays yt-dlp once the probe is ok) ---











def test_constraints_pin_ytdlp_to_current_stable_release():
    constraints = Path(__file__).parents[1] / "constraints.txt"
    pin = next(
        line
        for line in constraints.read_text(encoding="utf-8").splitlines()
        if line.startswith("yt-dlp==")
    )

    assert pin == "yt-dlp==2026.8.19"


def test_project_installs_official_ytdlp_default_dependencies():
    root = Path(__file__).parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    constraints = (root / "constraints.txt").read_text(encoding="utf-8")

    assert '"yt-dlp[default]==2026.8.19"' in pyproject
    assert "yt-dlp-ejs==0.8.0" in constraints




# --- check(): transcription readiness surfaced (deno present so JS path is ok) ---









# --- TLS trust store ---

def test_ytdlp_uses_system_trust_store_when_ssl_cert_file_is_set(monkeypatch):
    from agent_reach.channels import youtube

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    assert "no-certifi" not in youtube._ytdlp_argv("--version")
    monkeypatch.setenv("SSL_CERT_FILE", "/etc/ssl/corp-bundle.pem")
    argv = youtube._ytdlp_argv("--version")
    assert argv[argv.index("--compat-options") + 1] == "no-certifi"


# --- subtitle track choice ---

def _track(translated=False):
    tail = "&tlang=zh-Hans" if translated else ""
    return [{"ext": "vtt", "url": f"https://www.youtube.com/api/timedtext?v=x{tail}"}]


def test_subtitle_prefers_manual_track_over_machine_translation():
    from agent_reach.channels.youtube import _pick_subtitle_track

    info = {
        "subtitles": {"en": _track()},
        "automatic_captions": {"en": _track(), "en-orig": _track(), "zh-Hans": _track(translated=True)},
    }

    assert _pick_subtitle_track(info, ["zh-Hans", "zh", "en", "en-orig"]) == ("en", False)


def test_subtitle_prefers_original_auto_captions_over_translated_ones():
    from agent_reach.channels.youtube import _pick_subtitle_track

    info = {"automatic_captions": {"en-orig": _track(), "zh-Hans": _track(translated=True)}}

    assert _pick_subtitle_track(info, ["zh-Hans", "en-orig"]) == ("en-orig", True)


def test_subtitle_falls_back_to_translated_track_and_ignores_live_chat():
    from agent_reach.channels.youtube import _pick_subtitle_track

    info = {
        "subtitles": {"live_chat": _track()},
        "automatic_captions": {"zh-Hans": _track(translated=True)},
    }

    assert _pick_subtitle_track(info, ["live_chat", "zh-Hans"]) == ("zh-Hans", True)
    assert _pick_subtitle_track(info, ["fr"]) is None


def test_subtitle_downloads_only_the_chosen_track(monkeypatch):
    from agent_reach.channels import youtube

    info = {
        "title": "Demo",
        "subtitles": {"en": _track()},
        "automatic_captions": {"zh-Hans": _track(translated=True)},
    }
    calls = []

    def fake_run(args, timeout, cwd=None):
        calls.append(args)
        if "-J" in args:
            return json.dumps(info)
        Path(cwd, "x.en.vtt").write_text("WEBVTT\n\n00:00.000 --> 00:01.000\nhello\n", encoding="utf-8")
        return ""

    monkeypatch.setattr(youtube, "_run_ytdlp", fake_run)
    items = YouTubeChannel()._ytdlp_subtitle(target="C33hJGt-ySg", lang="zh-Hans,zh,en,en-orig", timeout=30)

    download = calls[-1]
    assert download[download.index("--sub-langs") + 1] == "en"
    assert "--write-subs" in download and "--write-auto-subs" not in download
    assert (items[0]["title"], items[0]["text"], items[0]["raw"]) == ("Demo", "hello", {"lang": "en"})


def test_subtitle_without_wanted_track_is_not_found_and_skips_download(monkeypatch):
    import pytest

    from agent_reach.channels import youtube
    from agent_reach.runtime.result import NOT_FOUND, ReachError

    calls = []

    def fake_run(args, timeout, cwd=None):
        calls.append(args)
        return json.dumps({"subtitles": {"de": _track()}})

    monkeypatch.setattr(youtube, "_run_ytdlp", fake_run)
    with pytest.raises(ReachError) as caught:
        YouTubeChannel()._ytdlp_subtitle(target="C33hJGt-ySg", lang="en", timeout=30)

    assert caught.value.code == NOT_FOUND
    assert len(calls) == 1

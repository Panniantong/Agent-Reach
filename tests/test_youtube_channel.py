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









# --- subtitle track choice: one track, never a needless machine translation ---

import json  # noqa: E402
import os  # noqa: E402

import pytest  # noqa: E402

from agent_reach.channels import youtube  # noqa: E402
from agent_reach.runtime.result import ReachError  # noqa: E402

_ES = ["es", "es-ES", "es-419", "en"]


def test_pick_prefers_human_subtitles_in_a_wanted_language():
    info = {"language": "en", "subtitles": {"en": [{}], "es": [{}]}, "automatic_captions": {"en-orig": [{}], "es": [{}]}}
    assert youtube._pick_subtitle_track(info, _ES) == ("es", False, False)


def test_pick_uses_original_language_auto_captions_before_any_translation():
    # Every language shows up in automatic_captions; only the original is not a translation.
    info = {"language": "en", "subtitles": {}, "automatic_captions": {"en-orig": [{}], "en": [{}], "es": [{}], "zh-Hans": [{}]}}
    assert youtube._pick_subtitle_track(info, _ES) == ("en-orig", True, False)


def test_pick_falls_back_to_spoken_language_when_no_orig_track():
    info = {"language": "fr", "subtitles": {"live_chat": [{}]}, "automatic_captions": {"fr": [{}], "es": [{}]}}
    assert youtube._pick_subtitle_track(info, _ES) == ("fr", True, False)


def test_pick_translates_only_as_last_resort_and_reports_none():
    info = {"subtitles": {}, "automatic_captions": {"es": [{}]}}
    assert youtube._pick_subtitle_track(info, _ES) == ("es", True, True)
    with pytest.raises(ReachError, match="no subtitles"):
        youtube._pick_subtitle_track({"subtitles": {}, "automatic_captions": {}}, _ES)


def test_subtitle_downloads_exactly_one_track_from_the_fetched_info(monkeypatch):
    info = {"id": "jTwm4xs5y4c", "title": "4 Rust tips", "language": "en",
            "subtitles": {}, "automatic_captions": {"en-orig": [{}], "es": [{}]}}
    calls = []

    def fake_run(args, timeout, cwd=None):
        calls.append(args)
        if "--dump-json" in args:
            return json.dumps(info)
        with open(os.path.join(cwd, "jTwm4xs5y4c.en-orig.vtt"), "w", encoding="utf-8") as fh:
            fh.write("WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nbuild a honeycomb\n")
        return ""

    monkeypatch.setattr(youtube, "_run_ytdlp", fake_run)
    items = YouTubeChannel()._ytdlp_subtitle(target="jTwm4xs5y4c", lang=",".join(_ES), timeout=30)
    download = calls[1]
    assert len(calls) == 2 and "--load-info-json" in download
    assert download[download.index("--sub-langs") + 1] == "en-orig" and "--write-auto-subs" in download
    assert items[0]["title"] == "4 Rust tips" and "honeycomb" in items[0]["text"]
    assert items[0]["raw"]["lang"] == "en-orig" and items[0]["raw"]["translated"] is False


# --- video channel: TikTok and Instagram Reels through the same yt-dlp helpers ---

from agent_reach.channels import video  # noqa: E402
from agent_reach.channels.video import VideoChannel  # noqa: E402


@pytest.mark.parametrize("url", [
    "https://www.tiktok.com/@scout2015/video/6718335390845095173",
    "https://vm.tiktok.com/ZMabc123/",
    "https://www.instagram.com/reel/C9xYz12AbCd/",
    "https://www.instagram.com/reels/C9xYz12AbCd",
    "https://www.instagram.com/p/C9xYz12AbCd/",
    "https://www.instagram.com/someone/reel/C9xYz12AbCd/",
])
def test_video_channel_accepts_tiktok_and_reel_links(url):
    assert VideoChannel().can_handle(url)


@pytest.mark.parametrize("url", [
    "https://www.instagram.com/someone/",
    "https://www.instagram.com/explore/tags/rust/",
    "https://tiktok.com.evil.test/video/1",
    "https://www.youtube.com/shorts/jTwm4xs5y4c",
])
def test_video_channel_rejects_profiles_lookalikes_and_other_sites(url):
    assert not VideoChannel().can_handle(url)


def test_read_routes_reels_to_video_not_instagram():
    from agent_reach.channels import get_all_channels
    readers = [ch for ch in get_all_channels() if any(a.name == "read" for a in ch.actions) and ch.name != "web"]
    reel = "https://www.instagram.com/reel/C9xYz12AbCd/"
    assert next(ch.name for ch in readers if ch.can_handle(reel)) == "video"


def test_video_transcribe_and_subtitle_reuse_the_shared_helpers(monkeypatch):
    seen = {}
    monkeypatch.setattr(video, "whisper_transcribe", lambda url, cookies, timestamps=False: seen.setdefault("transcribe", url) and [])
    monkeypatch.setattr(video, "ytdlp_subtitle",
                        lambda url, lang, timeout, cookies: seen.setdefault("subtitle", (url, lang)) and [])
    url = "https://www.tiktok.com/@scout2015/video/6718335390845095173"
    VideoChannel()._whisper_transcribe(target=url, timeout=10)
    VideoChannel()._ytdlp_subtitle(target=url, lang="es", timeout=10)
    assert seen == {"transcribe": url, "subtitle": (url, "es")}


def test_video_hands_the_saved_instagram_login_to_ytdlp_only_for_instagram(monkeypatch):
    rows = [{"name": "sessionid", "value": "abc", "domain": ".instagram.com", "path": "/",
             "secure": True, "expires": 1900000000.5}]
    monkeypatch.setattr(video, "_instagram_cookies", lambda: rows)
    seen = {}

    def fake_info(url, timeout, cookies):
        seen[url] = open(cookies, encoding="utf-8").read() if cookies else None
        return []

    monkeypatch.setattr(video, "ytdlp_info", fake_info)
    reel = "https://www.instagram.com/reel/C9xYz12AbCd/"
    tiktok = "https://www.tiktok.com/@scout2015/video/6718335390845095173"
    VideoChannel()._ytdlp_read(target=reel, timeout=10)
    VideoChannel()._ytdlp_read(target=tiktok, timeout=10)
    assert seen[reel].splitlines()[1] == ".instagram.com\tTRUE\t/\tTRUE\t1900000000\tsessionid\tabc"
    assert seen[tiktok] is None


def test_video_ignores_instagram_cookies_without_a_login(monkeypatch):
    from agent_reach.runtime import browser, cdp
    monkeypatch.setattr(browser, "is_running", lambda: True)
    monkeypatch.setattr(cdp, "cookies", lambda domain: [{"name": "csrftoken", "value": "x", "domain": ".instagram.com"}])
    assert video._instagram_cookies() == []


def test_video_links_drop_share_tracking_parameters():
    reel = "https://www.instagram.com/reel/DemkNsYu8og/?utm_source=ig_web_copy_link&srtk=MzRlODBiNWFlZA=="
    tiktok = "https://www.tiktok.com/@scout2015/video/6718335390845095173?is_from_webapp=1&sender_device=pc"
    assert video._video_url(reel) == "https://www.instagram.com/reel/DemkNsYu8og/"
    assert video._video_url(tiktok) == "https://www.tiktok.com/@scout2015/video/6718335390845095173"

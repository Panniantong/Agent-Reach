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











# --- playlist links ---
#
# A link opened from a playlist or a Mix looks like watch?v=<id>&list=<playlist>.
# Without --no-playlist yt-dlp extracts every entry of the playlist, so `read`
# would return another video's metadata and `subtitle` another video's captions.

PLAYLIST_LINK = "https://www.youtube.com/watch?v=jNQXAC9IVRw&list=PLAYLIST1"


def test_read_of_a_playlist_link_asks_ytdlp_for_the_single_video(monkeypatch):
    import json

    import agent_reach.channels.youtube as yt

    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return json.dumps({"id": "jNQXAC9IVRw", "title": "Me at the zoo",
                           "webpage_url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"})

    monkeypatch.setattr(yt, "run_cmd", fake_run)
    items = YouTubeChannel()._ytdlp_read(target=PLAYLIST_LINK, timeout=30)

    assert items[0]["title"] == "Me at the zoo"
    assert "--no-playlist" in seen["argv"]


def test_subtitle_of_a_playlist_link_asks_ytdlp_for_the_single_video(monkeypatch):
    import agent_reach.channels.youtube as yt

    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        Path(kwargs["cwd"], "jNQXAC9IVRw.en.vtt").write_text(
            "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nzoo words\n", encoding="utf-8")
        return "Me at the zoo\n"

    monkeypatch.setattr(yt, "run_cmd", fake_run)
    items = YouTubeChannel()._ytdlp_subtitle(target=PLAYLIST_LINK, lang="en", timeout=30)

    assert items[0]["text"] == "zoo words"
    assert "--no-playlist" in seen["argv"]


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

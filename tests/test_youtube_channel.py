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









# --- TLS trust store ---

def test_ytdlp_uses_system_trust_store_when_ssl_cert_file_is_set(monkeypatch):
    from agent_reach.channels import youtube

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    assert "no-certifi" not in youtube._ytdlp_argv("--version")
    monkeypatch.setenv("SSL_CERT_FILE", "/etc/ssl/corp-bundle.pem")
    argv = youtube._ytdlp_argv("--version")
    assert argv[argv.index("--compat-options") + 1] == "no-certifi"


def test_subtitle_prefers_original_speech_over_machine_translation(monkeypatch, tmp_path):
    from agent_reach.channels import youtube
    from agent_reach.runtime.dispatch import run_action

    tracks = {"en": "translated words", "ar-orig": "الكلام الأصلي"}

    def fake_ytdlp(args, timeout, cwd=None):
        requested = args[args.index("--sub-langs") + 1].split(",")
        selected = tracks if ".*-orig" in requested else [code for code in requested if code in tracks]
        for code in selected:
            Path(cwd, f"H0OuQdDeIJ4.{code}.vtt").write_text(
                f"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n{tracks[code]}\n",
                encoding="utf-8",
            )
        return "Arabic video\n"

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(youtube, "_run_ytdlp", fake_ytdlp)

    out = run_action(
        YouTubeChannel(),
        "subtitle",
        {"target": "H0OuQdDeIJ4"},
        only_backend="yt-dlp",
    )

    assert out["ok"] is True
    assert out["items"][0]["raw"]["lang"] == "ar-orig"
    assert out["items"][0]["text"] == "الكلام الأصلي"

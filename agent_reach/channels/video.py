# -*- coding: utf-8 -*-
"""Short videos from TikTok and Instagram Reels through yt-dlp, without opening a page.

This channel never logs in. When the user has logged in to Instagram themself
(`agent-reach login instagram`), the Agent Reach browser's Instagram cookies are
handed to yt-dlp, so reels limited to logged-in viewers can be read too; without
that session only public posts work.

To see the video, the agent transcribes it (each line carries its `[m:ss]`),
picks the moments whose image explains what is said, and asks `frames` for them.
"""

import json
import os
import re
from contextlib import contextmanager
from urllib.parse import urlsplit

from agent_reach.runtime.result import BAD_INPUT, ReachError, make_item
from agent_reach.utils.paths import (
    PrivatePathError,
    atomic_write_private_text,
    private_temporary_directory,
    read_small_text_no_follow,
)
from agent_reach.utils.url import host_matches

from .base import Action, Channel, Param
from .youtube import whisper_transcribe, ytdlp_info, ytdlp_subtitle

_TIKTOK = ("tiktok.com",)
_INSTAGRAM = ("instagram.com",)
_INSTAGRAM_VIDEO_PATH = re.compile(r"^/(?:[^/]+/)?(?:reels?|p|tv)/[A-Za-z0-9_-]+/?$")


def _video_url(target: str) -> str:
    t = str(target).strip()
    candidate = t if "://" in t else f"https://{t}"
    parts = urlsplit(candidate)
    # Share links carry tracking tokens (utm_*, srtk, is_from_webapp...); the path identifies the video.
    clean = f"{parts.scheme}://{parts.netloc}{parts.path}"
    if host_matches(candidate, *_TIKTOK):
        return clean
    if host_matches(candidate, *_INSTAGRAM) and _INSTAGRAM_VIDEO_PATH.match(parts.path):
        return clean
    raise ReachError(BAD_INPUT, "target must be a TikTok video link or an Instagram reel/post link")


def _instagram_cookies() -> list:
    """Instagram cookies of the Agent Reach browser, or [] when it holds no login.

    Live from the running browser, else from the session snapshot it saves.
    """
    from agent_reach.runtime import browser, cdp

    rows = cdp.cookies("instagram.com") if browser.is_running() else []
    if not rows:
        try:
            text = read_small_text_no_follow(browser.browser_root() / "session.json", max_bytes=2 * 1024 * 1024)
            rows = [c for c in json.loads(text or "{}").get("cookies", [])
                    if isinstance(c, dict) and cdp.domain_matches(c.get("domain", ""), "instagram.com")]
        except (OSError, ValueError, PrivatePathError):
            rows = []
    return rows if any(c.get("name") == "sessionid" and c.get("value") for c in rows) else []


def _netscape(rows: list) -> str:
    lines = ["# Netscape HTTP Cookie File"]
    for c in rows:
        domain = c["domain"]
        expires = c.get("expires", 0)
        expires = int(expires) if isinstance(expires, (int, float)) and expires > 0 else 0
        lines.append("\t".join([
            domain, "TRUE" if domain.startswith(".") else "FALSE", c.get("path") or "/",
            "TRUE" if c.get("secure") else "FALSE", str(expires), c["name"], c.get("value", ""),
        ]))
    return "\n".join(lines) + "\n"


@contextmanager
def _cookie_file(url: str):
    """Path of a private cookie file for an Instagram link with a saved login, else None."""
    rows = _instagram_cookies() if host_matches(url, *_INSTAGRAM) else []
    if not rows:
        yield None
        return
    with private_temporary_directory(prefix="agent-reach-cookies-") as tmp:
        path = os.path.join(tmp, "cookies.txt")
        atomic_write_private_text(path, _netscape(rows))
        yield path


class VideoChannel(Channel):
    name = "video"
    description = "Vídeos cortos públicos de TikTok e Instagram Reels"

    level = "default"
    #: transcribe re-encodes and chunks audio; frames cuts stills from the video
    prereqs = ("ffmpeg",)
    actions = (
        Action(
            "read",
            "Caption, author, date and stats of a TikTok video or Instagram reel",
            (Param("target", "TikTok or Instagram reel link"),),
            (("yt-dlp", "_ytdlp_read"),),
            live_test={"target": "https://www.tiktok.com/@scout2015/video/6718335390845095173"},
        ),
        Action(
            "subtitle",
            "Subtitle text when the video has captions (one track, never machine-translated first)",
            (
                Param("target", "TikTok or Instagram reel link"),
                Param("lang", "preferred languages for human subtitles, comma separated; otherwise the video's own language",
                      required=False, default="es,es-ES,es-419,en"),
            ),
            (("yt-dlp", "_ytdlp_subtitle"),),
        ),
        Action(
            "transcribe",
            "Speech-to-text of the video's audio, one `[m:ss] text` line per segment (uses Groq/OpenAI Whisper quota)",
            (Param("target", "TikTok or Instagram reel link"),),
            (("whisper", "_whisper_transcribe"),),
            timeout=600,
        ),
        Action(
            "frames",
            "Still images of the video at chosen moments, saved as JPEG files to open and look at",
            (
                Param("target", "TikTok or Instagram reel link"),
                Param("at", "moments to capture, comma separated seconds or m:ss (e.g. 0:03,0:12,27.5), "
                      "picked from the timestamped transcript; empty spreads 6 frames evenly",
                      required=False, default=""),
            ),
            (("ffmpeg", "_ffmpeg_frames"),),
            timeout=900,
        ),
    )

    def can_handle(self, url: str) -> bool:
        try:
            _video_url(url)
        except ReachError:
            return False
        return True

    def validate_params(self, action, params):
        params["target"] = _video_url(params["target"])

    # ── unified entry backends ──

    def _ytdlp_read(self, *, target: str, timeout: float) -> list:
        url = _video_url(target)
        with _cookie_file(url) as cookies:
            return ytdlp_info(url, timeout, cookies)

    def _ytdlp_subtitle(self, *, target: str, lang: str, timeout: float) -> list:
        url = _video_url(target)
        with _cookie_file(url) as cookies:
            return ytdlp_subtitle(url, lang, timeout, cookies)

    def _whisper_transcribe(self, *, target: str, timeout: float) -> list:
        url = _video_url(target)
        with _cookie_file(url) as cookies:
            return whisper_transcribe(url, cookies, timestamps=True)

    def _ffmpeg_frames(self, *, target: str, at: str, timeout: float) -> list:
        from agent_reach.frames import extract_frames, parse_moments
        from agent_reach.transcribe import TranscribeError

        url = _video_url(target)
        try:
            parse_moments(at)
        except ValueError as exc:
            raise ReachError(BAD_INPUT, str(exc)) from None
        try:
            with _cookie_file(url) as cookies:
                frames = extract_frames(url, at, cookies=cookies)
        except TranscribeError as exc:
            raise ReachError("UPSTREAM_BROKEN", str(exc)[:300]) from None
        return [make_item(title=f"frame at {f['clock']}", url=url, text=f["path"], raw=f) for f in frames]

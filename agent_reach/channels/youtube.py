# -*- coding: utf-8 -*-
"""YouTube — check if yt-dlp is available with JS runtime."""

import shutil

from agent_reach.probe import probe_command
from agent_reach.utils.paths import get_ytdlp_config_path, render_ytdlp_fix_command
from agent_reach.utils.text import read_utf8_text

from .base import Channel


def _has_js_runtime_config(config_path) -> bool:
    """Return whether yt-dlp config explicitly enables a JS runtime."""
    try:
        if not config_path.exists():
            return False
        return "--js-runtimes" in read_utf8_text(config_path)
    except OSError:
        return False


class YouTubeChannel(Channel):
    name = "youtube"
    description = "YouTube videos and subtitles"
    backends = ["yt-dlp"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "youtube.com" in d or "youtu.be" in d

    def check(self, config=None):
        # Actually run yt-dlp --version for liveness check, distinguish not installed / venv broken / can't run
        probe = probe_command("yt-dlp", ["--version"], timeout=10, package="yt-dlp")
        if probe.status == "missing":
            self.active_backend = None
            return "off", "yt-dlp not installed. Install: pip install yt-dlp"
        if probe.status == "broken":
            self.active_backend = None
            return "error", f"yt-dlp installed but can't execute\n{probe.hint}"
        if not probe.ok:  # timeout / error: installed but can't run
            self.active_backend = None
            detail = probe.hint or probe.output or probe.status
            return "error", f"yt-dlp can't run normally: {detail}"
        # yt-dlp itself is alive; subsequent JS runtime/transcription checks only affect ok/warn, not backend assignment
        self.active_backend = "yt-dlp"
        # Check JS runtime
        has_js = shutil.which("deno") or shutil.which("node")
        if not has_js:
            return "warn", (
                "yt-dlp installed but missing JS runtime (required by YouTube).\n"
                "  Install Node.js or deno, then run: agent-reach install"
            )
        # Check yt-dlp config for --js-runtimes
        # Deno works out of the box; Node.js requires explicit config
        has_deno = shutil.which("deno")
        if not has_deno:
            ytdlp_config = get_ytdlp_config_path()
            if not _has_js_runtime_config(ytdlp_config):
                return "warn", (
                    f"yt-dlp installed but JS runtime not configured. Run:\n  {render_ytdlp_fix_command()}"
                )
        # Surface transcription readiness so `doctor` reports it.
        msg = "Can extract video info and subtitles"
        if config is not None:
            providers = []
            if config.is_configured("groq_whisper"):
                providers.append("groq")
            if config.is_configured("openai_whisper"):
                providers.append("openai")
            if providers:
                if not shutil.which("ffmpeg"):
                    msg += " (audio transcription requires ffmpeg)"
                else:
                    msg += f", can transcribe audio ({'→'.join(providers)})"
        return "ok", msg

    def transcribe(self, url: str, *, provider: str = "auto", config=None) -> str:
        """Download a YouTube video's audio and return its transcript.

        Delegates to :func:`agent_reach.transcribe.transcribe`. Imported lazily
        so the channel module stays cheap to import for users who never
        transcribe.
        """
        from agent_reach.transcribe import transcribe as _transcribe

        return _transcribe(url, provider=provider, config=config)


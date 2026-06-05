# -*- coding: utf-8 -*-
"""YouTube — check if yt-dlp is available with JS runtime."""

import shutil

from agent_reach.utils.paths import get_ytdlp_config_path, render_ytdlp_fix_command
from agent_reach.utils.text import read_utf8_text

from .base import Channel


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
        if not shutil.which("yt-dlp"):
            return "off", "yt-dlp not installed. Install: pip install yt-dlp"
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
            has_js_config = False
            if ytdlp_config.exists():
                has_js_config = "--js-runtimes" in read_utf8_text(ytdlp_config)
            if not has_js_config:
                return "warn", (
                    "yt-dlp installed but JS runtime not configured. Run:\n"
                    f"  {render_ytdlp_fix_command()}"
                )
        return "ok", "Can extract video info and subtitles"

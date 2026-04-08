# -*- coding: utf-8 -*-
"""YouTube channel checks."""

from __future__ import annotations

import shutil

from agent_reach.utils.commands import find_command
from agent_reach.utils.paths import get_ytdlp_config_path, render_ytdlp_fix_command
from agent_reach.utils.text import read_utf8_text

from .base import Channel


class YouTubeChannel(Channel):
    name = "youtube"
    description = "YouTube video metadata and subtitles"
    backends = ["yt-dlp"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        host = urlparse(url).netloc.lower()
        return "youtube.com" in host or "youtu.be" in host

    def check(self, config=None):
        if not find_command("yt-dlp"):
            return "off", "yt-dlp is missing. Install it with winget install --id yt-dlp.yt-dlp -e"

        has_deno = bool(shutil.which("deno"))
        has_node = bool(shutil.which("node"))
        if not has_deno and not has_node:
            return "warn", "yt-dlp is installed but no JS runtime was found. Install Node.js or Deno"

        if has_deno:
            return "ok", "Ready to inspect video metadata and subtitles"

        config_path = get_ytdlp_config_path()
        if not config_path.exists():
            return "warn", (
                "yt-dlp needs a JS runtime config when Node.js is used.\n"
                f"  {render_ytdlp_fix_command()}"
            )

        if "--js-runtimes" not in read_utf8_text(config_path):
            return "warn", (
                "yt-dlp is installed but Node.js is not wired in yet.\n"
                f"  {render_ytdlp_fix_command()}"
            )

        return "ok", "Ready to inspect video metadata and subtitles"

# -*- coding: utf-8 -*-
"""YouTube — check if yt-dlp is available with JS runtime."""

import shutil

from agent_reach.utils.paths import get_ytdlp_config_path, render_ytdlp_fix_command
from agent_reach.utils.text import read_utf8_text

from .base import Channel


class YouTubeChannel(Channel):
    name = "youtube"
    description = "YouTube 视频和字幕"
    description_en = "YouTube videos and subtitles"
    backends = ["yt-dlp"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "youtube.com" in d or "youtu.be" in d

    def check(self, config=None):
        from agent_reach.lang import use_english

        if not shutil.which("yt-dlp"):
            if use_english():
                return "off", "yt-dlp not installed. Install: pip install yt-dlp"
            return "off", "yt-dlp 未安装。安装：pip install yt-dlp"
        # Check JS runtime
        has_js = shutil.which("deno") or shutil.which("node")
        if not has_js:
            if use_english():
                return "warn", (
                    "yt-dlp installed but missing JS runtime (required by YouTube).\n"
                    "  Install Node.js or deno, then run: agent-reach install"
                )
            return "warn", (
                "yt-dlp 已安装但缺少 JS runtime（YouTube 必须）。\n"
                "  安装 Node.js 或 deno，然后运行：agent-reach install"
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
                if use_english():
                    return "warn", (
                        "yt-dlp installed but JS runtime not configured. Run:\n"
                        f"  {render_ytdlp_fix_command()}"
                    )
                return "warn", (
                    "yt-dlp 已安装但未配置 JS runtime。运行：\n"
                    f"  {render_ytdlp_fix_command()}"
                )
        if use_english():
            return "ok", "Can extract video info and subtitles"
        return "ok", "可提取视频信息和字幕"

# -*- coding: utf-8 -*-
"""YouTube — check if yt-dlp is available with JS runtime."""

import os
import shutil
from .base import Channel


class YouTubeChannel(Channel):
    name = "youtube"
    description = "YouTube 视频和字幕"
    backends = ["yt-dlp"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "youtube.com" in d or "youtu.be" in d

    def check(self, config=None):
        if not shutil.which("yt-dlp"):
            return "off", "yt-dlp 未安装。安装：pip install yt-dlp"
        # Check JS runtime
        has_js = shutil.which("deno") or shutil.which("node")
        if not has_js:
            return "warn", (
                "yt-dlp 已安装但缺少 JS runtime（YouTube 必须）。\n"
                "  安装 Node.js 或 deno，然后运行：agent-reach install"
            )
        # Check yt-dlp config for --js-runtimes
        ytdlp_config = os.path.expanduser("~/.config/yt-dlp/config")
        has_deno = shutil.which("deno")
        if not has_deno and os.path.exists(ytdlp_config):
            with open(ytdlp_config, "r") as f:
                if "--js-runtimes" not in f.read():
                    return "warn", (
                        "yt-dlp 已安装但未配置 JS runtime。运行：\n"
                        "  mkdir -p ~/.config/yt-dlp && echo '--js-runtimes node' >> ~/.config/yt-dlp/config"
                    )
        return "ok", "可提取视频信息和字幕"

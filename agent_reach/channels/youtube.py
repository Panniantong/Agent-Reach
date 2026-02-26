# -*- coding: utf-8 -*-
"""YouTube — check if yt-dlp is available."""

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
        if shutil.which("yt-dlp"):
            return "ok", "可提取视频信息和字幕"
        return "off", "yt-dlp 未安装。安装：pip install yt-dlp"

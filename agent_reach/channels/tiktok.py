# -*- coding: utf-8 -*-
"""TikTok — check if yt-dlp is available for public videos."""

import shutil

from .base import Channel


class TikTokChannel(Channel):
    name = "tiktok"
    description = "TikTok 短视频"
    backends = ["yt-dlp"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "tiktok.com" in d or "vm.tiktok.com" in d

    def check(self, config=None):
        if not shutil.which("yt-dlp"):
            return "off", (
                "yt-dlp 未安装。安装：pip install yt-dlp\n  支持公开视频的元数据和字幕提取。"
            )
        return "ok", "可提取公开视频元数据和字幕"

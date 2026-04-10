# -*- coding: utf-8 -*-
"""Facebook — check if yt-dlp is available for public posts and videos."""

import shutil
from .base import Channel


class FacebookChannel(Channel):
    name = "facebook"
    description = "Facebook 公开帖子和视频"
    backends = ["yt-dlp", "Jina Reader"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "facebook.com" in d or "fb.com" in d or "fb.watch" in d

    def check(self, config=None):
        if not shutil.which("yt-dlp"):
            return "off", (
                "yt-dlp 未安装。安装：pip install yt-dlp\n"
                "  支持公开视频。文字帖子可通过 Jina Reader 读取。"
            )
        return "ok", "可提取公开视频元数据；文字帖子可通过 Jina Reader 读取"

# -*- coding: utf-8 -*-
"""Instagram — check if yt-dlp is available for public posts and reels."""

import shutil

from .base import Channel


class InstagramChannel(Channel):
    name = "instagram"
    description = "Instagram 公开帖子和 Reels"
    backends = ["yt-dlp"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "instagram.com" in d or "instagr.am" in d

    def check(self, config=None):
        if not shutil.which("yt-dlp"):
            return "off", (
                "yt-dlp 未安装。安装：pip install yt-dlp\n"
                "  支持公开帖子和 Reels，私密内容需登录 cookie。"
            )
        return "ok", "可提取公开帖子和 Reels 的元数据（需 cookie 访问私密内容）"

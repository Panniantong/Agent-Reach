# -*- coding: utf-8 -*-
"""Bilibili — check if yt-dlp is available."""

import os
import shutil
from .base import Channel


class BilibiliChannel(Channel):
    name = "bilibili"
    description = "B站视频和字幕"
    backends = ["yt-dlp"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "bilibili.com" in d or "b23.tv" in d

    def check(self, config=None):
        if not shutil.which("yt-dlp"):
            return "off", "yt-dlp 未安装。安装：pip install yt-dlp"
        proxy = (config.get("bilibili_proxy") if config else None) or os.environ.get("BILIBILI_PROXY")
        if proxy:
            return "ok", "可提取视频信息和字幕（代理已配置）"
        return "ok", "可提取视频信息和字幕（本地环境）。服务器可能需要代理"

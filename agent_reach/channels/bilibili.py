# -*- coding: utf-8 -*-
"""Bilibili — video via yt-dlp, search/browse via bili-cli or API."""

import json
import os
import shutil
import subprocess
import urllib.request
from .base import Channel

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_TIMEOUT = 10
_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/all/v2?keyword=test&page=1"


def _search_api_ok() -> bool:
    """Return True if Bilibili search API responds with code 0."""
    req = urllib.request.Request(_SEARCH_API, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
            return data.get("code") == 0
    except Exception:
        return False


class BilibiliChannel(Channel):
    name = "bilibili"
    description = "B站视频、字幕和搜索"
    backends = ["yt-dlp", "bili-cli (可选)", "B站搜索 API"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "bilibili.com" in d or "b23.tv" in d

    def check(self, config=None):
        if not shutil.which("yt-dlp"):
            return "off", "yt-dlp 未安装。安装：pip install yt-dlp"

        proxy = (config.get("bilibili_proxy") if config else None) or os.environ.get("BILIBILI_PROXY")
        has_bili_cli = bool(shutil.which("bili"))

        parts = []

        # 视频读取状态
        if proxy:
            parts.append("视频读取：yt-dlp（代理已配置）")
        else:
            parts.append("视频读取：yt-dlp")

        # bili-cli 增强
        if has_bili_cli:
            parts.append("搜索/热门/排行：bili-cli 可用")
        else:
            # 检测搜索 API 连通性
            api_ok = _search_api_ok()
            if api_ok:
                parts.append("搜索：B站 API 可用")
            else:
                parts.append("搜索：B站 API 不可达")
            parts.append("提示：安装 bili-cli 可解锁热门/排行/动态：pipx install bilibili-cli")

        status = "ok" if has_bili_cli or _search_api_ok() else "warn"
        return status, "。".join(parts)

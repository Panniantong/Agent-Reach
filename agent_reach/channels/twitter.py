# -*- coding: utf-8 -*-
"""Twitter/X — check if bird CLI is available."""

import shutil
import subprocess
from .base import Channel


class TwitterChannel(Channel):
    name = "twitter"
    description = "Twitter/X 推文"
    backends = ["bird CLI"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "x.com" in d or "twitter.com" in d

    def check(self, config=None):
        bird = shutil.which("bird") or shutil.which("birdx")
        if not bird:
            return "warn", (
                "bird CLI 未安装。搜索可通过 Exa 替代。安装：\n"
                "  npm install -g @steipete/bird"
            )
        try:
            r = subprocess.run(
                [bird, "whoami"], capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0:
                return "ok", "完整可用（读取、搜索推文）"
            return "warn", (
                "bird CLI 已安装但未配置 Cookie。运行：\n"
                "  agent-reach configure twitter-cookies \"auth_token=xxx; ct0=yyy\""
            )
        except Exception:
            return "warn", "bird CLI 已安装但连接失败"

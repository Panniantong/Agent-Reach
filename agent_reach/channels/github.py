# -*- coding: utf-8 -*-
"""GitHub — check if gh CLI is available."""

import shutil
import subprocess
from .base import Channel


class GitHubChannel(Channel):
    name = "github"
    description = "GitHub 仓库和代码"
    backends = ["gh CLI"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        return "github.com" in urlparse(url).netloc.lower()

    def check(self, config=None):
        if not shutil.which("gh"):
            return "warn", "gh CLI 未安装。安装：https://cli.github.com"
        try:
            subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True, text=True, timeout=5
            )
            return "ok", "完整可用（读取、搜索、Fork、Issue、PR 等）"
        except Exception:
            return "ok", "gh CLI 已装但未认证。运行 gh auth login 可解锁完整功能"

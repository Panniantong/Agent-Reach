# -*- coding: utf-8 -*-
"""GitHub — check if gh CLI is available."""

import shutil
import subprocess
from .base import Channel


class GitHubChannel(Channel):
    name = "github"
    description = "GitHub 仓库和代码"
    description_en = "GitHub repos and code"
    backends = ["gh CLI"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        return "github.com" in urlparse(url).netloc.lower()

    def check(self, config=None):
        from agent_reach.lang import use_english

        gh = shutil.which("gh")
        if not gh:
            if use_english():
                return "warn", "gh CLI not installed. Install: https://cli.github.com"
            return "warn", "gh CLI 未安装。安装：https://cli.github.com"
        try:
            r = subprocess.run(
                [gh, "auth", "status"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=5
            )
            if r.returncode == 0:
                if use_english():
                    return "ok", "Fully available (read, search, Fork, Issue, PR, etc.)"
                return "ok", "完整可用（读取、搜索、Fork、Issue、PR 等）"
            if use_english():
                return "warn", "gh CLI installed but not authenticated. Run gh auth login to unlock full functionality"
            return "warn", "gh CLI 已安装但未认证。运行 gh auth login 可解锁完整功能"
        except Exception:
            if use_english():
                return "warn", "gh CLI status check failed. Run gh auth status for details"
            return "warn", "gh CLI 状态检查失败，运行 gh auth status 查看详情"

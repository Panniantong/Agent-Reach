# -*- coding: utf-8 -*-
"""Twitter/X — check if twitter-cli or bird CLI is available."""

import shutil
import subprocess
from .base import Channel


class TwitterChannel(Channel):
    name = "twitter"
    description = "Twitter/X 推文"
    description_en = "Twitter/X tweets"
    backends = ["twitter-cli", "bird CLI (legacy)"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "x.com" in d or "twitter.com" in d

    def check(self, config=None):
        from agent_reach.lang import use_english

        # Prefer twitter-cli, fallback to bird/birdx
        twitter = shutil.which("twitter")
        bird = shutil.which("bird") or shutil.which("birdx")

        if twitter:
            return self._check_twitter_cli(twitter)
        elif bird:
            return self._check_bird(bird)
        else:
            if use_english():
                return "warn", (
                    "Twitter CLI not installed. Install:\n"
                    "  pipx install twitter-cli\n"
                    "or:\n"
                    "  uv tool install twitter-cli"
                )
            return "warn", (
                "Twitter CLI 未安装。安装方式：\n"
                "  pipx install twitter-cli\n"
                "或：\n"
                "  uv tool install twitter-cli"
            )

    def _check_twitter_cli(self, binary: str):
        from agent_reach.lang import use_english

        try:
            r = subprocess.run(
                [binary, "status"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=10
            )
            output = (r.stdout or "") + (r.stderr or "")
            if r.returncode == 0 and "ok: true" in output:
                if use_english():
                    return "ok", (
                        "twitter-cli fully available (search, read tweets, timeline, "
                        "articles, user queries, Threads)"
                    )
                return "ok", (
                    "twitter-cli 完整可用（搜索、读推文、时间线、长文/Article、"
                    "用户查询、Thread）"
                )
            if "not_authenticated" in output:
                if use_english():
                    return "warn", (
                        "twitter-cli installed but not authenticated. Set up with:\n"
                        "  export TWITTER_AUTH_TOKEN=\"xxx\"\n"
                        "  export TWITTER_CT0=\"yyy\"\n"
                        "or make sure you're logged into x.com in your browser"
                    )
                return "warn", (
                    "twitter-cli 已安装但未认证。设置方式：\n"
                    "  export TWITTER_AUTH_TOKEN=\"xxx\"\n"
                    "  export TWITTER_CT0=\"yyy\"\n"
                    "或确保已在浏览器中登录 x.com"
                )
            if use_english():
                return "warn", (
                    "twitter-cli installed but auth check failed. Run:\n"
                    "  twitter -v status for details"
                )
            return "warn", (
                "twitter-cli 已安装但认证检查失败。运行：\n"
                "  twitter -v status 查看详细信息"
            )
        except Exception:
            if use_english():
                return "warn", "twitter-cli installed but connection failed"
            return "warn", "twitter-cli 已安装但连接失败"

    def _check_bird(self, binary: str):
        from agent_reach.lang import use_english

        try:
            r = subprocess.run(
                [binary, "check"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=10
            )
            output = (r.stdout or "") + (r.stderr or "")
            if r.returncode == 0:
                if use_english():
                    return "ok", "bird CLI available (read and search tweets, including articles)"
                return "ok", "bird CLI 可用（读取、搜索推文，含长文/X Article）"
            if "Missing credentials" in output or "missing" in output.lower():
                if use_english():
                    return "warn", (
                        "bird CLI installed but credentials not configured. Set:\n"
                        "  export AUTH_TOKEN=\"xxx\"\n"
                        "  export CT0=\"yyy\""
                    )
                return "warn", (
                    "bird CLI 已安装但未配置认证。设置环境变量：\n"
                    "  export AUTH_TOKEN=\"xxx\"\n"
                    "  export CT0=\"yyy\""
                )
            if use_english():
                return "warn", (
                    "bird CLI installed but auth check failed."
                )
            return "warn", (
                "bird CLI 已安装但认证检查失败。"
            )
        except Exception:
            if use_english():
                return "warn", "bird CLI installed but connection failed"
            return "warn", "bird CLI 已安装但连接失败"

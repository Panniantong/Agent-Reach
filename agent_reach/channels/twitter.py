# -*- coding: utf-8 -*-
"""Twitter/X — check if twitter-cli (public-clis/twitter-cli) is available."""

import shutil
import subprocess
from .base import Channel


class TwitterChannel(Channel):
    name = "twitter"
    description = "Twitter/X 推文"
    backends = ["twitter-cli"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "x.com" in d or "twitter.com" in d

    def check(self, config=None):
        twitter = shutil.which("twitter")
        if not twitter:
            return "warn", (
                "twitter-cli 未安装。安装方式：\n"
                "  pipx install twitter-cli\n"
                "或：\n"
                "  uv tool install twitter-cli"
            )

        try:
            r = subprocess.run(
                [twitter, "status"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=10
            )
            output = (r.stdout or "") + (r.stderr or "")
            if r.returncode == 0 and "ok: true" in output:
                return "ok", (
                    "完整可用（搜索、读推文、时间线、长文/Article、"
                    "用户查询、Thread）"
                )
            if "not_authenticated" in output:
                return "warn", (
                    "twitter-cli 已安装但未认证。设置方式：\n"
                    "  export TWITTER_AUTH_TOKEN=\"xxx\"\n"
                    "  export TWITTER_CT0=\"yyy\"\n"
                    "或确保已在浏览器中登录 x.com"
                )
            return "warn", (
                "twitter-cli 已安装但认证检查失败。运行：\n"
                "  twitter -v status 查看详细信息"
            )
        except Exception:
            return "warn", "twitter-cli 已安装但连接失败"

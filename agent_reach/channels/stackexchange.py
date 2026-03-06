# -*- coding: utf-8 -*-
"""Stack Exchange — Q&A search across 170+ sites (StackOverflow, Bioinformatics, etc.)."""

import subprocess
from .base import Channel


class StackExchangeChannel(Channel):
    name = "stackexchange"
    description = "Stack Exchange 问答（StackOverflow 等 170+ 子站）"
    backends = ["Stack Exchange API"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return any(x in d for x in [
            "stackoverflow.com", "stackexchange.com",
            "superuser.com", "serverfault.com",
            "askubuntu.com", "mathoverflow.net",
        ])

    def check(self, config=None):
        try:
            r = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 "--compressed",
                 "https://api.stackexchange.com/2.3/info?site=stackoverflow",
                 "--connect-timeout", "10"],
                capture_output=True, encoding="utf-8", timeout=15,
            )
            if r.stdout.strip() == "200":
                return "ok", "Stack Exchange API 可用（免费，无需 API Key，300 请求/天）"
            return "warn", f"Stack Exchange API 返回 HTTP {r.stdout.strip()}"
        except Exception as e:
            return "warn", f"Stack Exchange API 连接失败：{e}"

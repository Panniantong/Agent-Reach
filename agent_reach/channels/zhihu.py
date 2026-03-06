# -*- coding: utf-8 -*-
"""知乎 (Zhihu) — Q&A platform via zhihuMcpServer."""

import shutil
import subprocess
from .base import Channel


class ZhihuChannel(Channel):
    name = "zhihu"
    description = "知乎问答与专栏"
    backends = ["zhihuMcpServer"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "zhihu.com" in d

    def check(self, config=None):
        # zhihuMcpServer runs via npx from GitHub clone
        npx = shutil.which("npx")
        if not npx:
            return "off", (
                "需要 Node.js。安装后克隆 zhihuMcpServer：\n"
                "  git clone https://github.com/morrain/zhihuMcpServer.git\n"
                "  cd zhihuMcpServer && npm install && npm run build"
            )
        # Check if mcporter has zhihu configured
        mcporter = shutil.which("mcporter")
        if mcporter:
            try:
                r = subprocess.run(
                    [mcporter, "config", "list"], capture_output=True,
                    encoding="utf-8", errors="replace", timeout=5
                )
                if "zhihu" in r.stdout.lower():
                    return "ok", "知乎 MCP 已配置（需扫码登录后使用）"
            except Exception:
                pass
        return "warn", (
            "需要安装 zhihuMcpServer（知乎 MCP 服务）：\n"
            "  git clone https://github.com/morrain/zhihuMcpServer.git\n"
            "  cd zhihuMcpServer && npm install && npm run build\n"
            "  mcporter config add zhihu --stdio \"node /path/to/zhihuMcpServer/build/index.js\"\n"
            "  # 启动后需扫码登录知乎"
        )

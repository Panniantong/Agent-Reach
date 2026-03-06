# -*- coding: utf-8 -*-
"""Weibo (微博) — check if mcporter + weibo MCP server is available."""

import shutil
import subprocess
from .base import Channel


class WeiboChannel(Channel):
    name = "weibo"
    description = "微博动态和热搜"
    backends = ["mcp-server-weibo"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "weibo.com" in d or "weibo.cn" in d

    def check(self, config=None):
        mcporter = shutil.which("mcporter")
        if not mcporter:
            return "off", (
                "需要 mcporter + mcp-server-weibo。安装步骤：\n"
                "  1. npm install -g mcporter\n"
                "  2. docker run -d --name mcp-server-weibo -p 4200:4200 mcp-server-weibo\n"
                "     或：uvx mcp-server-weibo（需要 uv）\n"
                "  3. mcporter config add weibo http://localhost:4200/mcp\n"
                "  详见 https://github.com/qinyuanpei/mcp-server-weibo"
            )
        try:
            r = subprocess.run(
                [mcporter, "config", "list"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            if "weibo" not in r.stdout:
                return "off", (
                    "mcporter 已装但微博 MCP 未配置。运行：\n"
                    "  docker run -d --name mcp-server-weibo -p 4200:4200 mcp-server-weibo\n"
                    "  mcporter config add weibo http://localhost:4200/mcp"
                )
        except Exception:
            return "off", "mcporter 连接异常"
        try:
            r = subprocess.run(
                [mcporter, "call", "weibo.get_hot_searches()"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=10
            )
            if r.returncode == 0 and r.stdout.strip():
                return "ok", "完整可用（热搜、搜索用户/内容、读动态）"
            return "warn", "MCP 已连接但调用异常，检查 mcp-server-weibo 服务是否在运行"
        except Exception:
            return "warn", "MCP 连接异常，检查 mcp-server-weibo 服务是否在运行"

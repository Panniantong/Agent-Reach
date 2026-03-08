# -*- coding: utf-8 -*-
"""Weibo (微博) — check if mcporter + mcp-server-weibo is available."""

import shutil
import subprocess
from .base import Channel


class WeiboChannel(Channel):
    name = "weibo"
    description = "微博动态与热搜"
    backends = ["mcp-server-weibo"]
    tier = 1

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
                "  2. pip install git+https://github.com/Panniantong/mcp-server-weibo.git\n"
                "  3. mcporter config add weibo --command 'mcp-server-weibo'\n"
                "  详见 https://github.com/Panniantong/mcp-server-weibo"
            )
        try:
            r = subprocess.run(
                [mcporter, "config", "list"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            if "weibo" not in r.stdout:
                return "off", (
                    "mcporter 已装但微博 MCP 未配置。运行：\n"
                    "  pip install git+https://github.com/Panniantong/mcp-server-weibo.git\n"
                    "  mcporter config add weibo --command 'mcp-server-weibo'"
                )
        except Exception:
            return "off", "mcporter 连接异常"
        try:
            r = subprocess.run(
                [mcporter, "list", "weibo"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=15
            )
            if r.returncode == 0 and "search_users" in r.stdout:
                return "ok", "完整可用（热搜、搜索、用户动态、评论）"
            return "warn", "MCP 已配置但工具加载失败，检查 mcp-server-weibo 版本"
        except Exception:
            return "warn", "MCP 连接异常，检查 mcp-server-weibo 是否可用"

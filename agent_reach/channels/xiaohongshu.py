# -*- coding: utf-8 -*-
"""XiaoHongShu — check if mcporter + xiaohongshu MCP is available."""

import shutil
import subprocess
from .base import Channel


class XiaoHongShuChannel(Channel):
    name = "xiaohongshu"
    description = "小红书笔记"
    backends = ["xiaohongshu-mcp"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "xiaohongshu.com" in d or "xhslink.com" in d

    def check(self, config=None):
        if not shutil.which("mcporter"):
            return "off", (
                "需要 mcporter + xiaohongshu-mcp。安装步骤：\n"
                "  1. npm install -g mcporter\n"
                "  2. docker run -d --name xiaohongshu-mcp -p 18060:18060 xpzouying/xiaohongshu-mcp\n"
                "  3. mcporter config add xiaohongshu http://localhost:18060/mcp\n"
                "  详见 https://github.com/xpzouying/xiaohongshu-mcp"
            )
        try:
            r = subprocess.run(
                ["mcporter", "list"], capture_output=True, text=True, timeout=10
            )
            if "xiaohongshu" not in r.stdout:
                return "off", (
                    "mcporter 已装但小红书 MCP 未配置。运行：\n"
                    "  docker run -d --name xiaohongshu-mcp -p 18060:18060 xpzouying/xiaohongshu-mcp\n"
                    "  mcporter config add xiaohongshu http://localhost:18060/mcp"
                )
        except Exception:
            return "off", "mcporter 连接异常"
        try:
            r = subprocess.run(
                ["mcporter", "call", "xiaohongshu.check_login_status()"],
                capture_output=True, text=True, timeout=10
            )
            if "已登录" in r.stdout or "logged" in r.stdout.lower():
                return "ok", "完整可用（阅读、搜索、发帖、评论、点赞）"
            return "warn", "MCP 已连接但未登录，需扫码登录"
        except Exception:
            return "warn", "MCP 连接异常，检查 xiaohongshu-mcp 服务是否在运行"

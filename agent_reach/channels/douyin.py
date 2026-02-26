# -*- coding: utf-8 -*-
"""Douyin (抖音) — check if mcporter + douyin-mcp-server is available."""

import shutil
import subprocess
from .base import Channel


class DouyinChannel(Channel):
    name = "douyin"
    description = "抖音短视频"
    backends = ["douyin-mcp-server"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "douyin.com" in d or "iesdouyin.com" in d

    def check(self, config=None):
        if not shutil.which("mcporter"):
            return "off", (
                "需要 mcporter + douyin-mcp-server。安装步骤：\n"
                "  1. npm install -g mcporter\n"
                "  2. pip install douyin-mcp-server\n"
                "  3. 启动服务（见下方说明）\n"
                "  4. mcporter config add douyin http://localhost:18070/mcp\n"
                "  详见 https://github.com/yzfly/douyin-mcp-server"
            )
        try:
            r = subprocess.run(
                ["mcporter", "list"], capture_output=True, text=True, timeout=10
            )
            if "douyin" not in r.stdout:
                return "off", (
                    "mcporter 已装但抖音 MCP 未配置。运行：\n"
                    "  pip install douyin-mcp-server\n"
                    "  # 启动服务后：\n"
                    "  mcporter config add douyin http://localhost:18070/mcp"
                )
        except Exception:
            return "off", "mcporter 连接异常"
        try:
            r = subprocess.run(
                ["mcporter", "call", "douyin.parse_douyin_video_info(share_link: \"https://www.douyin.com\")"],
                capture_output=True, text=True, timeout=15
            )
            if r.returncode == 0:
                return "ok", "完整可用（视频解析、下载链接获取）"
            return "warn", "MCP 已连接但调用异常，检查 douyin-mcp-server 服务是否在运行"
        except Exception:
            return "warn", "MCP 连接异常，检查 douyin-mcp-server 服务是否在运行"

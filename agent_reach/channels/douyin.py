# -*- coding: utf-8 -*-
"""Douyin (抖音) — check if mcporter + douyin-mcp-server is available."""

import shutil
import subprocess
from .base import Channel


class DouyinChannel(Channel):
    name = "douyin"
    description = "抖音短视频"
    description_en = "Douyin videos"
    backends = ["douyin-mcp-server"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "douyin.com" in d or "iesdouyin.com" in d

    def check(self, config=None):
        from agent_reach.lang import use_english

        mcporter = shutil.which("mcporter")
        if not mcporter:
            if use_english():
                return "off", (
                    "mcporter + douyin-mcp-server required. Steps:\n"
                    "  1. npm install -g mcporter\n"
                    "  2. pip install douyin-mcp-server\n"
                    "  3. Start the service (see docs below)\n"
                    "  4. mcporter config add douyin http://localhost:18070/mcp\n"
                    "  See https://github.com/yzfly/douyin-mcp-server"
                )
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
                [mcporter, "config", "list"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            if "douyin" not in r.stdout:
                if use_english():
                    return "off", (
                        "mcporter installed but Douyin MCP not configured. Run:\n"
                        "  pip install douyin-mcp-server\n"
                        "  # After starting the service:\n"
                        "  mcporter config add douyin http://localhost:18070/mcp"
                    )
                return "off", (
                    "mcporter 已装但抖音 MCP 未配置。运行：\n"
                    "  pip install douyin-mcp-server\n"
                    "  # 启动服务后：\n"
                    "  mcporter config add douyin http://localhost:18070/mcp"
                )
        except Exception:
            if use_english():
                return "off", "mcporter connection error"
            return "off", "mcporter 连接异常"
        # Verify MCP connectivity by listing available tools instead of
        # calling with a hardcoded (invalid) share link that always fails.
        try:
            r = subprocess.run(
                [mcporter, "list", "douyin"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=15
            )
            if r.returncode == 0 and r.stdout.strip():
                if use_english():
                    return "ok", "Fully available (video parsing, download link retrieval)"
                return "ok", "完整可用（视频解析、下载链接获取）"
            if use_english():
                return "warn", "MCP connected but tool list empty, check douyin-mcp-server is running"
            return "warn", "MCP 已连接但工具列表为空，检查 douyin-mcp-server 服务是否在运行"
        except Exception:
            if use_english():
                return "warn", "MCP connection error, check douyin-mcp-server is running"
            return "warn", "MCP 连接异常，检查 douyin-mcp-server 服务是否在运行"

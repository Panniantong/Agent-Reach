# -*- coding: utf-8 -*-
"""Douyin (抖音) — check if mcporter + douyin-mcp-server is available."""

import os
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
        # Preferred mode: built-in scripts shipped with Agent Reach.
        script = os.path.expanduser("~/.local/bin/agent-reach")
        has_python = bool(shutil.which("python3"))
        has_ffmpeg = bool(shutil.which("ffmpeg"))

        has_requests = False
        has_ffmpeg_python = False
        if has_python:
            try:
                subprocess.run(["python3", "-c", "import requests"], capture_output=True, timeout=5, check=True)
                has_requests = True
            except Exception:
                pass
            try:
                subprocess.run(["python3", "-c", "import ffmpeg"], capture_output=True, timeout=5, check=True)
                has_ffmpeg_python = True
            except Exception:
                pass

        if has_python and has_ffmpeg and has_requests and has_ffmpeg_python:
            has_api_key = bool(os.environ.get("API_KEY"))
            if has_api_key:
                return "ok", "完整可用（脚本模式：视频解析、下载、文案提取）"
            return "warn", "可解析和下载抖音视频；文案提取需配置 API_KEY（硅基流动）"

        # Fallback mode: mcporter + douyin-mcp-server.
        mcporter = shutil.which("mcporter")
        if not mcporter:
            return "off", (
                "抖音能力未完整安装。优先方案：安装 Agent Reach 自带抖音脚本依赖（python requests ffmpeg-python + ffmpeg）；\n"
                "兼容方案：mcporter + douyin-mcp-server。安装步骤：\n"
                "  1. npm install -g mcporter\n"
                "  2. pip install douyin-mcp-server\n"
                "  3. 启动服务\n"
                "  4. mcporter config add douyin http://localhost:18070/mcp"
            )
        try:
            r = subprocess.run(
                [mcporter, "config", "list"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=5
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
                [mcporter, "list", "douyin"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=15
            )
            if r.returncode == 0 and r.stdout.strip():
                return "ok", "MCP 模式可用（视频解析、下载链接获取）"
            return "warn", "MCP 已连接但工具列表为空，检查 douyin-mcp-server 服务是否在运行"
        except Exception:
            return "warn", "MCP 连接异常，检查 douyin-mcp-server 服务是否在运行"

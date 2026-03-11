# -*- coding: utf-8 -*-
"""Douyin (抖音) — check if built-in script workflow is available."""

import os
import shutil
import subprocess
from .base import Channel


class DouyinChannel(Channel):
    name = "douyin"
    description = "抖音短视频"
    backends = ["built-in scripts", "siliconflow-sensevoice(optional)"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "douyin.com" in d or "iesdouyin.com" in d

    def check(self, config=None):
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

        missing = []
        if not has_python:
            missing.append("python3")
        if not has_ffmpeg:
            missing.append("ffmpeg")
        if not has_requests:
            missing.append("requests")
        if not has_ffmpeg_python:
            missing.append("ffmpeg-python")
        return "off", (
            "抖音脚本能力未完整安装。缺少依赖：" + ", ".join(missing) + "。\n"
            "安装建议：\n"
            "  pip install requests ffmpeg-python\n"
            "  Ubuntu/Debian: apt install -y ffmpeg\n"
            "  macOS: brew install ffmpeg\n"
            "如需文案提取，还需配置 API_KEY（硅基流动）。"
        )

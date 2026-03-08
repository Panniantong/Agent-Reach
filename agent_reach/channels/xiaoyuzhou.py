# -*- coding: utf-8 -*-
"""Xiaoyuzhou Podcast (小宇宙播客) — transcribe podcasts via Groq Whisper API."""

import os
import shutil
from .base import Channel


class XiaoyuzhouChannel(Channel):
    name = "xiaoyuzhou"
    description = "小宇宙播客转文字"
    backends = ["groq-whisper", "ffmpeg"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "xiaoyuzhoufm.com" in d

    def check(self, config=None):
        # Check ffmpeg
        if not shutil.which("ffmpeg"):
            return "off", (
                "需要 ffmpeg（音频转码和切片）。安装：\n"
                "  Ubuntu/Debian: apt install -y ffmpeg\n"
                "  macOS: brew install ffmpeg"
            )

        # Check script exists
        script = os.path.expanduser("~/.agent-reach/tools/xiaoyuzhou/transcribe.sh")
        if not os.path.isfile(script):
            return "off", (
                "转录脚本未安装。运行：\n"
                "  agent-reach install --env=auto\n"
                "  或手动复制 transcribe.sh 到 ~/.agent-reach/tools/xiaoyuzhou/"
            )

        # Check GROQ_API_KEY
        if not os.environ.get("GROQ_API_KEY"):
            # Check if saved in config
            config_path = os.path.expanduser("~/.agent-reach/config.json")
            has_key = False
            if os.path.isfile(config_path):
                try:
                    import json
                    with open(config_path) as f:
                        cfg = json.load(f)
                    has_key = bool(cfg.get("groq_api_key"))
                except Exception:
                    pass
            if not has_key:
                return "warn", (
                    "需要配置 Groq API Key（免费）。步骤：\n"
                    "  1. 注册 https://console.groq.com\n"
                    "  2. 运行: agent-reach configure groq-api-key gsk_xxxxx"
                )

        return "ok", "完整可用（播客下载 + Whisper 转录）"

# -*- coding: utf-8 -*-
"""Xiaoyuzhou Podcast (小宇宙播客) — transcribe podcasts via Groq Whisper API."""

import os
from agent_reach.config import Config
from agent_reach.probe import probe_command
from agent_reach.paths import xiaoyuzhou_tools_dir
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
        self.active_backend = None

        # Check ffmpeg — really execute it: a stale pip-installed ffmpeg shim
        # passes shutil.which() but cannot run
        probe = probe_command("ffmpeg", ["-version"], timeout=10, package="ffmpeg")
        if probe.status == "missing":
            return "off", (
                "需要 ffmpeg（音频转码和切片）。安装：\n"
                "  Ubuntu/Debian: apt install -y ffmpeg\n"
                "  macOS: brew install ffmpeg"
            )
        if not probe.ok:
            return "error", (
                "ffmpeg 无法执行，重装：brew install ffmpeg（macOS）/ apt install ffmpeg（Linux）"
            )

        # Check script exists
        script = str(xiaoyuzhou_tools_dir() / "transcribe.sh")
        if not os.path.isfile(script):
            return "off", (
                "转录脚本未安装。运行：\n"
                "  agent-reach install --env=auto\n"
                "  或手动复制 transcribe.sh 到 ~/.agent-reach/tools/xiaoyuzhou/"
            )

        # Check GROQ_API_KEY — prefer env var, fall back to Agent Reach config
        has_key = bool(os.environ.get("GROQ_API_KEY"))
        if not has_key:
            try:
                cfg = config if config is not None else Config()
                has_key = bool(cfg.get("groq_api_key"))
            except Exception:
                has_key = False
        if not has_key:
            return "warn", (
                "需要配置 Groq API Key（免费）。步骤：\n"
                "  1. 注册 https://console.groq.com\n"
                "  2. 运行: agent-reach configure groq-key gsk_xxxxx"
            )

        self.active_backend = "groq-whisper"
        return "ok", "完整可用（播客下载 + Whisper 转录）"

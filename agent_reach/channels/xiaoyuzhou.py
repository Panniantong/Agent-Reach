# -*- coding: utf-8 -*-
"""Xiaoyuzhou Podcast — transcribe podcasts via Groq Whisper API."""

import os
import shutil
from agent_reach.config import Config
from .base import Channel


class XiaoyuzhouChannel(Channel):
    name = "xiaoyuzhou"
    description = "Xiaoyuzhou podcast transcription"
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
                "ffmpeg required (audio transcoding and segmentation). Install:\n"
                "  Ubuntu/Debian: apt install -y ffmpeg\n"
                "  macOS: brew install ffmpeg"
            )

        # Check script exists
        script = os.path.expanduser("~/.agent-reach/tools/xiaoyuzhou/transcribe.sh")
        if not os.path.isfile(script):
            return "off", (
                "Transcription script not installed. Run:\n"
                "  agent-reach install --env=auto\n"
                "  or manually copy transcribe.sh to ~/.agent-reach/tools/xiaoyuzhou/"
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
                "Groq API Key required (free). Steps:\n"
                "  1. Sign up at https://console.groq.com\n"
                "  2. Run: agent-reach configure groq-key gsk_xxxxx"
            )

        return "ok", "Fully available (podcast download + Whisper transcription)"

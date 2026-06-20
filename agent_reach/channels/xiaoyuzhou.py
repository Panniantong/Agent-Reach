# -*- coding: utf-8 -*-
"""Xiaoyuzhou Podcast (小宇宙播客) — transcribe podcasts via Groq Whisper API."""

import os
from agent_reach.config import Config
from agent_reach.probe import probe_command
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
        self.active_backend = None

        # Check ffmpeg — really execute it: a stale pip-installed ffmpeg shim
        # passes shutil.which() but cannot run
        probe = probe_command("ffmpeg", ["-version"], timeout=10, package="ffmpeg")
        if probe.status == "missing":
            return "off", (
                "ffmpeg required (audio transcoding and slicing). Install:\n"
                "  Ubuntu/Debian: apt install -y ffmpeg\n"
                "  macOS: brew install ffmpeg"
            )
        if not probe.ok:
            return "error", (
                "ffmpeg can't execute, reinstall: brew install ffmpeg (macOS) / apt install ffmpeg (Linux)"
            )

        # Check script exists
        script = os.path.expanduser("~/.agent-reach/tools/xiaoyuzhou/transcribe.sh")
        if not os.path.isfile(script):
            return "off", (
                "Transcription script not installed. Run:\n"
                "  agent-reach install --env=auto\n"
                "  Or manually copy transcribe.sh to ~/.agent-reach/tools/xiaoyuzhou/"
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
                "  1. Register at https://console.groq.com\n"
                "  2. Run: agent-reach configure groq-key gsk_xxxxx"
            )

        self.active_backend = "groq-whisper"
        return "ok", "Fully available (podcast download + Whisper transcription)"

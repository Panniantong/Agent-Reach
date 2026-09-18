# -*- coding: utf-8 -*-
"""Xiaoyuzhou Podcast — transcribe podcasts via Groq Whisper API."""

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
        from agent_reach.utils.url import host_matches

        return host_matches(url, "xiaoyuzhoufm.com")

    def check(self, config=None):
        self.active_backend = None

        # Check ffmpeg — really execute it: a stale pip-installed ffmpeg shim
        # passes shutil.which() but cannot run
        probe = probe_command("ffmpeg", ["-version"], timeout=10, package="ffmpeg")
        if probe.status == "missing":
            return "off", (
                "ffmpeg is required for audio transcoding and chunking. Install:\n"
                "  Ubuntu/Debian: apt install -y ffmpeg\n"
                "  macOS: brew install ffmpeg"
            )
        if not probe.ok:
            return "error", (
                "ffmpeg cannot execute. Reinstall with `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux)"
            )

        # Check script exists
        script = os.path.expanduser("~/.agent-reach/tools/xiaoyuzhou/transcribe.sh")
        if not os.path.isfile(script):
            return "off", (
                "The transcription script is not installed. Run:\n"
                "  agent-reach install --env=auto --system --channels=xiaoyuzhou\n"
                "  Or copy transcribe.sh manually to ~/.agent-reach/tools/xiaoyuzhou/"
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
                "A Groq API key is required. Steps:\n"
                "  1. Sign up at https://console.groq.com\n"
                "  2. Run: agent-reach configure groq-key (hidden input)"
            )

        self.active_backend = "groq-whisper"
        return "ok", "Fully available (podcast download + Whisper transcription)"

# -*- coding: utf-8 -*-
"""YouTube — check if yt-dlp is available with JS runtime."""

import shutil
from typing import Optional

from agent_reach.utils.paths import get_ytdlp_config_path, render_ytdlp_fix_command
from agent_reach.utils.text import read_utf8_text

from .base import Channel


class YouTubeChannel(Channel):
    name = "youtube"
    description = "YouTube 视频和字幕"
    backends = ["yt-dlp"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "youtube.com" in d or "youtu.be" in d

    def check(self, config=None):
        if not shutil.which("yt-dlp"):
            return "off", "yt-dlp 未安装。安装：pip install yt-dlp"
        # Check JS runtime
        has_js = shutil.which("deno") or shutil.which("node")
        if not has_js:
            return "warn", (
                "yt-dlp 已安装但缺少 JS runtime（YouTube 必须）。\n"
                "  安装 Node.js 或 deno，然后运行：agent-reach install"
            )
        # Check yt-dlp config for --js-runtimes
        # Deno works out of the box; Node.js requires explicit config
        has_deno = shutil.which("deno")
        if not has_deno:
            ytdlp_config = get_ytdlp_config_path()
            has_js_config = False
            if ytdlp_config.exists():
                has_js_config = "--js-runtimes" in read_utf8_text(ytdlp_config)
            if not has_js_config:
                return "warn", (
                    f"yt-dlp 已安装但未配置 JS runtime。运行：\n  {render_ytdlp_fix_command()}"
                )
        # Surface transcription readiness so `doctor` reports it.
        msg = "可提取视频信息和字幕"
        if config is not None:
            providers = []
            if config.is_configured("groq_whisper"):
                providers.append("groq")
            if config.is_configured("openai_whisper"):
                providers.append("openai")
            if providers:
                if not shutil.which("ffmpeg"):
                    msg += "（音频转写需安装 ffmpeg）"
                else:
                    msg += f"，可转写音频（{'→'.join(providers)}）"
        return "ok", msg

    def transcribe(self, url: str, *, provider: str = "auto", config=None) -> str:
        """Download a YouTube video's audio and return its transcript.

        Delegates to :func:`agent_reach.transcribe.transcribe`. Imported lazily
        so the channel module stays cheap to import for users who never
        transcribe.
        """
        from agent_reach.transcribe import transcribe as _transcribe

        return _transcribe(url, provider=provider, config=config)

    @staticmethod
    def transcription_providers(config) -> list:
        """Return the list of configured transcription providers (in fallback order)."""
        order = []
        if config and config.is_configured("groq_whisper"):
            order.append("groq")
        if config and config.is_configured("openai_whisper"):
            order.append("openai")
        return order

    # Re-export the helper for type hints in callers without re-importing.
    @staticmethod
    def transcription_supported() -> Optional[str]:
        """Return None if ffmpeg is available; otherwise an install hint."""
        if shutil.which("ffmpeg"):
            return None
        return "ffmpeg 未安装，无法转写音频。brew install ffmpeg / apt install ffmpeg"

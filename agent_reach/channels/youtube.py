# -*- coding: utf-8 -*-
"""YouTube — check if yt-dlp is available with JS runtime."""

import glob
import os
import shutil
import sys
import tempfile

from agent_reach.probe import probe_command
from agent_reach.utils.paths import get_ytdlp_config_path, render_ytdlp_fix_command
from agent_reach.utils.text import read_utf8_text

from .base import Channel


def _has_js_runtime_config(config_path) -> bool:
    """Return whether yt-dlp config explicitly enables a JS runtime."""
    try:
        if not config_path.exists():
            return False
        return "--js-runtimes" in read_utf8_text(config_path)
    except OSError:
        return False


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
        # 真跑 yt-dlp --version 探活，区分未装 / venv 断链 / 跑不动
        executable = shutil.which("yt-dlp")
        command = "yt-dlp" if executable else sys.executable
        args = ["--version"] if executable else ["-m", "yt_dlp", "--version"]
        probe = probe_command(command, args, timeout=10, package="yt-dlp")
        if probe.status == "missing":
            self.active_backend = None
            return "off", "yt-dlp 未安装。安装：pip install yt-dlp"
        if probe.status == "broken":
            self.active_backend = None
            return "error", f"yt-dlp 已安装但无法执行\n{probe.hint}"
        if not probe.ok:  # timeout / error：装了但跑不动
            self.active_backend = None
            detail = probe.hint or probe.output or probe.status
            return "error", f"yt-dlp 无法正常运行：{detail}"
        # yt-dlp 本体是活的；后面的 JS runtime/转写检查只影响 ok/warn，不影响后端归属
        self.active_backend = "yt-dlp"
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
            if not _has_js_runtime_config(ytdlp_config):
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

    def read_command(self, url: str):
        return [sys.executable, "-m", "yt_dlp", "--dump-single-json", "--skip-download", url]

    def extract_content(self, url: str, run_command):
        metadata = run_command(self.read_command(url))
        if not isinstance(metadata, dict):
            raise RuntimeError("yt-dlp did not return video metadata")

        manual = metadata.get("subtitles") or {}
        automatic = metadata.get("automatic_captions") or {}
        tracks = manual or automatic
        available = {key for key in tracks if key != "live_chat"}
        configured = [
            lang.strip() for lang in os.environ.get("AGENT_REACH_SUB_LANGS", "").split(",")
            if lang.strip()
        ]
        preferences = configured + [
            metadata.get("original_language"), metadata.get("language"), "en", "en-US", "en-GB"
        ]
        language = next((lang for lang in preferences if lang in available), None)
        if language is None and available:
            language = sorted(available)[0]
        if language is None:
            raise RuntimeError("no subtitles were available for this YouTube video")

        with tempfile.TemporaryDirectory(prefix="agent-reach-youtube-") as temp_dir:
            output = f"{temp_dir}/%(id)s"
            run_command(
                [
                    sys.executable, "-m", "yt_dlp", "--write-sub", "--write-auto-sub",
                    "--sub-langs", language, "--sub-format", "vtt", "--skip-download",
                    "-o", output, url,
                ],
                timeout=120,
            )
            subtitle_paths = sorted(glob.glob(f"{temp_dir}/*.vtt"))
            if not subtitle_paths:
                raise RuntimeError(f"subtitle track {language!r} could not be downloaded")
            transcript = "\n".join(_clean_vtt(path) for path in subtitle_paths)

        return {
            "content": transcript,
            "author": metadata.get("uploader") or metadata.get("channel"),
            "published_at": metadata.get("timestamp") or metadata.get("upload_date"),
            "media": [{"url": metadata["thumbnail"]}] if metadata.get("thumbnail") else [],
        }

    def transcribe(self, url: str, *, provider: str = "auto", config=None) -> str:
        """Download a YouTube video's audio and return its transcript.

        Delegates to :func:`agent_reach.transcribe.transcribe`. Imported lazily
        so the channel module stays cheap to import for users who never
        transcribe.
        """
        from agent_reach.transcribe import transcribe as _transcribe

        return _transcribe(url, provider=provider, config=config)


def _clean_vtt(path: str) -> str:
    """Remove VTT timing/metadata and collapse adjacent duplicate lines."""
    lines: list[str] = []
    with open(path, encoding="utf-8") as subtitle:
        for raw_line in subtitle:
            line = raw_line.strip()
            if not line or line == "WEBVTT" or "-->" in line or line.startswith(("Kind:", "Language:")):
                continue
            if line != (lines[-1] if lines else None):
                lines.append(line)
    return "\n".join(lines)

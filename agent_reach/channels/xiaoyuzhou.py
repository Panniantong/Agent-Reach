# -*- coding: utf-8 -*-
"""Xiaoyuzhou Podcast (小宇宙播客) — transcribe podcasts via Groq Whisper API."""

import os

from agent_reach.config import Config
from agent_reach.runtime.result import (
    BAD_INPUT, NEED_SETUP, NOT_FOUND, UPSTREAM_BROKEN, ReachError, make_item,
)
from agent_reach.runtime.run import run_cmd
from agent_reach.utils.paths import private_temporary_directory

from .base import Action, Channel, Param

_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "transcribe_xiaoyuzhou.sh")


class XiaoyuzhouChannel(Channel):
    name = "xiaoyuzhou"
    description = "小宇宙播客转文字"

    level = "optional"
    prereqs = ("ffmpeg",)
    def setup_problems(self):
        cfg = Config(read_only=True)
        if (os.environ.get("DEEPGRAM_API_KEY") or cfg.get("deepgram_api_key")
                or os.environ.get("GROQ_API_KEY") or cfg.get("groq_api_key")):
            return []
        return ["no transcription key: set `deepgram_api_key` (recommended) or `groq_api_key` "
                "via `agent-reach configure deepgram-key` / `groq-key`"]

    actions = (
        Action(
            "transcribe",
            "Full transcript of a podcast episode (uses Groq Whisper quota)",
            (
                Param("target", "episode link"),
                Param("max-seconds", "only process the first N seconds; the download "
                                     "uses a Range request so long episodes are not pulled whole",
                      required=False, type=int, default=None),
            ),
            (("deepgram", "_deepgram_transcribe"),
             ("groq-whisper", "_script_transcribe")),
            live_test={"target": "https://www.xiaoyuzhoufm.com/episode/6888a0148e06fe8de74811af",
                       "max-seconds": 30},
            timeout=900,
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "xiaoyuzhoufm.com")

    # ── unified entry backends ──

    def _deepgram_transcribe(self, *, target: str, timeout: float, **kwargs) -> list:
        """通过 transcribe.transcribe() 走 Deepgram；支持 max-seconds 截断。"""
        from agent_reach.transcribe import transcribe as _transcribe
        from agent_reach.utils.url import host_matches

        if not host_matches(str(target).strip(), "xiaoyuzhoufm.com"):
            raise ReachError(BAD_INPUT, "target must be a xiaoyuzhoufm.com episode link")
        seconds = _parse_max_seconds(kwargs)

        import tempfile
        from pathlib import Path

        audio = _fetch_episode_audio(str(target).strip(), seconds)
        with private_temporary_directory(prefix="agent-reach-xyz-dg-") as tmp:
            try:
                return [make_item(url=str(target).strip(),
                                  text=_transcribe(str(audio), provider="deepgram",
                                                   out_dir=Path(tmp)))]
            finally:
                try:
                    os.unlink(audio)
                except OSError:
                    pass

    def _script_transcribe(self, *, target: str, timeout: float,
                           **kwargs) -> list:
        from agent_reach.utils.url import host_matches

        if not host_matches(str(target).strip(), "xiaoyuzhoufm.com"):
            raise ReachError(BAD_INPUT, "target must be a xiaoyuzhoufm.com episode link")
        # 先校验参数，再检查密钥/依赖：坏参数不该报成"没配 key"
        raw_seconds = kwargs.get("max-seconds")
        seconds = None
        if raw_seconds is not None:
            try:
                seconds = int(raw_seconds)
            except (TypeError, ValueError):
                raise ReachError(BAD_INPUT, "max_seconds must be a positive integer")
            if seconds <= 0:
                raise ReachError(BAD_INPUT, "max_seconds must be a positive integer")
        key = os.environ.get("GROQ_API_KEY") or Config(read_only=True).get("groq_api_key")
        if not key:
            raise ReachError(
                NEED_SETUP, "no Groq API key configured",
                hint="Ask the user for a free key from https://console.groq.com, then run `agent-reach configure groq-key`.",
            )
        from agent_reach.runtime.tools import ffmpeg_path

        ffmpeg = ffmpeg_path()
        if not ffmpeg:
            raise ReachError(NEED_SETUP, "ffmpeg is not installed", hint="Run `agent-reach add xiaoyuzhou`.")
        # our private ffmpeg goes first on the script's PATH
        path = os.pathsep.join([os.path.dirname(ffmpeg), os.environ.get("PATH", "")])
        args = ["bash", _SCRIPT]
        if seconds is not None:
            args += ["--max-seconds", str(seconds)]
        args += [str(target).strip()]
        with private_temporary_directory(prefix="agent-reach-xyz-") as tmp:
            out = os.path.join(tmp, "transcript.txt")
            args.append(out)
            run_cmd(args, timeout=timeout,
                    env={"GROQ_API_KEY": str(key), "PATH": path, "TMPDIR": tmp}, label="transcribe")
            with open(out, encoding="utf-8", errors="replace") as fh:
                text = fh.read().strip()
        return [make_item(url=str(target).strip(), text=text)]

def _parse_max_seconds(kwargs) -> "int | None":
    """参数名带连字符（CLI 直接拼 flag），所以只能从 kwargs 取。"""
    raw = kwargs.get("max-seconds")
    if raw is None:
        return None
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        raise ReachError(BAD_INPUT, "max_seconds must be a positive integer")
    if seconds <= 0:
        raise ReachError(BAD_INPUT, "max_seconds must be a positive integer")
    return seconds


def _fetch_episode_audio(url: str, max_seconds: "int | None") -> str:
    """解析小宇宙页面拿音频直链。

    有 max_seconds 时用 Range 只拉开头一段（小宇宙 CDN 支持 Range），
    否则下载整集 —— 长播客整集可能 200MB+。
    """
    import re
    import subprocess
    import tempfile

    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
    page = subprocess.run(["curl", "-sL", "--fail", "--max-time", "60", "-A", ua, url],
                          capture_output=True, text=True)
    if page.returncode != 0:
        raise ReachError(UPSTREAM_BROKEN, "could not load the episode page")
    m = re.search(r'https://media\.xyzcdn\.net/[^"]*\.(?:m4a|mp3)', page.stdout)
    if not m:
        raise ReachError(NOT_FOUND, "no audio link found on the episode page")

    fd, path = tempfile.mkstemp(prefix="xyz-", suffix=".m4a")
    os.close(fd)
    cmd = ["curl", "-sL", "--fail", "--retry", "3", "--max-time", "1800", "-A", ua]
    if max_seconds:
        # 64kbps 单声道 ≈ 8KB/s，留 8 倍余量覆盖原始码率 + moov 索引
        cmd += ["-r", f"0-{max_seconds * 8192 * 8 - 1}"]
    cmd += ["-o", path, m.group(0)]
    if subprocess.run(cmd).returncode != 0:
        raise ReachError(UPSTREAM_BROKEN, "audio download failed")
    return path

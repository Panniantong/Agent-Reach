# -*- coding: utf-8 -*-
"""Xiaoyuzhou Podcast (小宇宙播客) — transcribe podcasts via Groq Whisper API."""

import os

from agent_reach.config import Config
from agent_reach.runtime.result import BAD_INPUT, NEED_SETUP, ReachError, make_item
from agent_reach.runtime.run import run_cmd
from agent_reach.utils.paths import private_temporary_directory

from .base import Action, Channel, Param

_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "transcribe_xiaoyuzhou.sh")


class XiaoyuzhouChannel(Channel):
    name = "xiaoyuzhou"
    description = "小宇宙播客转文字"

    level = "optional"
    prereqs = ("ffmpeg",)
    needs_key = "groq-key"

    def setup_problems(self):
        if os.environ.get("GROQ_API_KEY") or Config(read_only=True).get("groq_api_key"):
            return []
        return ["no Groq API key: get one free at https://console.groq.com, then `agent-reach configure groq-key`"]

    actions = (
        Action(
            "transcribe",
            "Full transcript of a podcast episode (uses Groq Whisper quota)",
            (Param("target", "episode link"),),
            (("groq-whisper", "_script_transcribe"),),
            timeout=900,
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "xiaoyuzhoufm.com")

    # ── unified entry backends ──

    def _script_transcribe(self, *, target: str, timeout: float) -> list:
        from agent_reach.utils.url import host_matches

        if not host_matches(str(target).strip(), "xiaoyuzhoufm.com"):
            raise ReachError(BAD_INPUT, "target must be a xiaoyuzhoufm.com episode link")
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
        with private_temporary_directory(prefix="agent-reach-xyz-") as tmp:
            out = os.path.join(tmp, "transcript.txt")
            run_cmd(["bash", _SCRIPT, str(target).strip(), out], timeout=timeout,
                    env={"GROQ_API_KEY": str(key), "PATH": path, "TMPDIR": tmp}, label="transcribe")
            with open(out, encoding="utf-8", errors="replace") as fh:
                text = fh.read().strip()
        return [make_item(url=str(target).strip(), text=text)]

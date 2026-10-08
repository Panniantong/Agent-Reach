# -*- coding: utf-8 -*-
"""YouTube — check if yt-dlp is available with JS runtime."""

import html
import json
import os
import re
import shutil
import sys
import tempfile

from agent_reach.probe import probe_command
from agent_reach.runtime.result import (
    BAD_INPUT,
    NEED_LOGIN,
    NOT_FOUND,
    RATE_LIMITED,
    ReachError,
    make_item,
)
from agent_reach.runtime.run import CommandFailed, run_cmd
from agent_reach.utils.paths import (
    PrivatePathError,
    get_ytdlp_config_path,
    read_small_text_no_follow,
    render_ytdlp_fix_command,
)

from .base import Action, Channel, Param

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_VTT_TIME_RE = re.compile(r"^\d{2}:\d{2}(:\d{2})?\.\d{3} --> ")
_TAG_RE = re.compile(r"<[^>]+>")
_RAW_KEYS = ("id", "duration", "view_count", "like_count", "channel_id", "tags", "categories")


def _ytdlp_argv(*args: str) -> list:
    """Run the yt-dlp bundled with Agent Reach (pinned via our dependencies)."""
    runtime = []
    if shutil.which("deno") is None and shutil.which("node"):
        runtime = ["--js-runtimes", "node"]
    return [sys.executable, "-m", "yt_dlp", "--no-warnings", *runtime, *args]


def _video_url(target: str) -> str:
    from agent_reach.utils.url import host_matches

    t = str(target).strip()
    if _VIDEO_ID_RE.match(t):
        return f"https://www.youtube.com/watch?v={t}"
    candidate = t if "://" in t else f"https://{t}"
    if host_matches(candidate, "youtube.com", "youtu.be"):
        return candidate
    raise ReachError(BAD_INPUT, "target must be a YouTube link or 11-character video id")


def _run_ytdlp(args: list, timeout: float, cwd=None) -> str:
    try:
        return run_cmd(_ytdlp_argv(*args), timeout=timeout, cwd=cwd, label="yt-dlp")
    except CommandFailed as exc:
        err = exc.stderr.lower()
        if any(s in err for s in ("video unavailable", "private video", "has been removed", "does not exist")):
            raise ReachError(NOT_FOUND, exc.message) from None
        if "sign in to confirm" in err:
            raise ReachError(
                NEED_LOGIN,
                exc.message,
                hint="YouTube is asking for a bot check. Ask the user whether to configure YouTube cookies; never sign in for them.",
            ) from None
        if "429" in err or "too many requests" in err:
            raise ReachError(RATE_LIMITED, exc.message) from None
        raise


def _iso_date(yyyymmdd) -> str:
    s = str(yyyymmdd or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 and s.isdigit() else ""


def vtt_to_text(vtt: str) -> str:
    """Plain text from WebVTT: drop headers, timings, tags; collapse auto-caption repeats."""
    out = []
    for line in vtt.splitlines():
        s = line.strip()
        if (
            not s
            or s == "WEBVTT"
            or s.startswith(("Kind:", "Language:", "NOTE", "STYLE"))
            or _VTT_TIME_RE.match(s)
            or s.isdigit()
        ):
            continue
        s = html.unescape(_TAG_RE.sub("", s)).strip()
        if s and (not out or out[-1] != s):
            out.append(s)
    return "\n".join(out)


_JS_RUNTIMES_SUPPORTED_FROM = (2025, 11, 12)
_YTDLP_UPGRADE_COMMAND = 'python -m pip install -U "yt-dlp[default]"'


def _parse_ytdlp_version(version: str):
    """Return a comparable stable yt-dlp release tuple, if recognised."""
    match = re.fullmatch(r"\s*(\d{4})\.(\d{1,2})\.(\d{1,2})\s*", version)
    return tuple(map(int, match.groups())) if match else None


def _has_js_runtime_config(config_path) -> bool:
    """Return whether yt-dlp config explicitly enables a JS runtime."""
    try:
        payload = read_small_text_no_follow(
            config_path,
            max_bytes=1024 * 1024,
        )
        return payload is not None and "--js-runtimes" in payload
    except (OSError, UnicodeError, PrivatePathError):
        return False


class YouTubeChannel(Channel):
    name = "youtube"
    description = "YouTube 视频和字幕"
    backends = ["yt-dlp"]
    tier = 0

    level = "default"
    actions = (
        Action(
            "read",
            "Video title, channel, date and description",
            (Param("target", "video link or id"),),
            (("yt-dlp", "_ytdlp_read"),),
            live_test={"target": "https://www.youtube.com/watch?v=jNQXAC9IVRw"},
        ),
        Action(
            "search",
            "Search videos",
            (
                Param("query", "what to search for"),
                Param("limit", "max results", required=False, type=int, default=5),
            ),
            (("yt-dlp", "_ytdlp_search"),),
            live_test={"query": "python tutorial", "limit": 2},
        ),
        Action(
            "subtitle",
            "Full subtitle text of a video (manual or auto captions)",
            (
                Param("target", "video link or id"),
                Param("lang", "preferred languages, comma separated", required=False, default="zh-Hans,zh,en,en-orig"),
            ),
            (("yt-dlp", "_ytdlp_subtitle"),),
            live_test={"target": "https://www.youtube.com/watch?v=jNQXAC9IVRw"},
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "youtube.com", "youtu.be")

    def check(self, config=None):
        # 真跑 yt-dlp --version 探活，区分未装 / venv 断链 / 跑不动
        probe = probe_command("yt-dlp", ["--version"], timeout=10, package="yt-dlp")
        if probe.status == "missing":
            self.active_backend = None
            return "off", f"yt-dlp 未安装。安装：{_YTDLP_UPGRADE_COMMAND}"
        if probe.status == "broken":
            self.active_backend = None
            return "error", (
                "yt-dlp 已安装但无法执行。重装（含 JS 支持）：\n"
                f"  {_YTDLP_UPGRADE_COMMAND}\n{probe.hint}"
            )
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
                "  安装 Node.js 或 deno，然后运行：agent-reach install --system"
            )
        # Check yt-dlp config for --js-runtimes
        # Deno works out of the box; Node.js requires explicit config
        has_deno = shutil.which("deno")
        if not has_deno:
            ytdlp_config = get_ytdlp_config_path()
            if not _has_js_runtime_config(ytdlp_config):
                version = _parse_ytdlp_version(probe.output)
                if version is None:
                    return "warn", (
                        "无法确认 yt-dlp 版本是否支持 JS runtime 配置。"
                        "请先升级并重新运行 doctor：\n"
                        f"  {_YTDLP_UPGRADE_COMMAND}"
                    )
                if version < _JS_RUNTIMES_SUPPORTED_FROM:
                    return "warn", (
                        "yt-dlp 版本过旧，不支持 JS runtime 配置。请先升级并重新运行 doctor：\n"
                        f"  {_YTDLP_UPGRADE_COMMAND}"
                    )
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
                missing_media_tools = [
                    tool
                    for tool in ("ffmpeg", "ffprobe")
                    if not shutil.which(tool)
                ]
                if missing_media_tools:
                    msg += (
                        "（音频转写需安装 "
                        + "、".join(missing_media_tools)
                        + "）"
                    )
                else:
                    msg += f"，可转写音频（{'/'.join(providers)}）"
        return "ok", msg

    def transcribe(
        self,
        url: str,
        *,
        provider: str = "auto",
        config=None,
        allow_provider_fallback: bool = False,
    ) -> str:
        """Download a YouTube video's audio and return its transcript.

        Delegates to :func:`agent_reach.transcribe.transcribe`. Imported lazily
        so the channel module stays cheap to import for users who never
        transcribe.
        """
        from agent_reach.transcribe import transcribe as _transcribe

        return _transcribe(
            url,
            provider=provider,
            config=config,
            allow_provider_fallback=allow_provider_fallback,
        )

    # ── unified entry backends ──

    def _ytdlp_read(self, *, target: str, timeout: float) -> list:
        out = _run_ytdlp(["--dump-json", "--skip-download", _video_url(target)], timeout)
        info = json.loads(out.splitlines()[-1])
        return [
            make_item(
                title=info.get("title"),
                url=info.get("webpage_url"),
                author=info.get("uploader") or info.get("channel"),
                published_at=_iso_date(info.get("upload_date")),
                text=info.get("description"),
                raw={k: info.get(k) for k in _RAW_KEYS},
            )
        ]

    def _ytdlp_search(self, *, query: str, limit: int, timeout: float) -> list:
        out = _run_ytdlp(["--flat-playlist", "--dump-json", f"ytsearch{limit}:{query}"], timeout)
        items = []
        for line in out.splitlines():
            if not line.strip():
                continue
            info = json.loads(line)
            vid = info.get("id")
            items.append(
                make_item(
                    title=info.get("title"),
                    url=info.get("url") or (f"https://www.youtube.com/watch?v={vid}" if vid else None),
                    author=info.get("channel") or info.get("uploader"),
                    text=info.get("description"),
                    raw={k: info.get(k) for k in _RAW_KEYS},
                )
            )
        return items

    def _ytdlp_subtitle(self, *, target: str, lang: str, timeout: float) -> list:
        url = _video_url(target)
        wanted = [x.strip() for x in lang.split(",") if x.strip()]
        with tempfile.TemporaryDirectory(prefix="agent-reach-subs-") as tmp:
            out = _run_ytdlp(
                [
                    "--skip-download", "--no-simulate",
                    "--write-subs", "--write-auto-subs",
                    "--sub-langs", ",".join(wanted), "--sub-format", "vtt",
                    "--print", "%(title)s",
                    "-o", "%(id)s.%(ext)s",
                    url,
                ],
                timeout,
                cwd=tmp,
            )
            files = [f for f in os.listdir(tmp) if f.endswith(".vtt")]
            if not files:
                raise ReachError(NOT_FOUND, f"no subtitles in {', '.join(wanted)} for this video")

            def rank(name: str) -> int:
                code = name.rsplit(".", 2)[-2] if name.count(".") >= 2 else ""
                return wanted.index(code) if code in wanted else len(wanted)

            best = min(files, key=rank)
            with open(os.path.join(tmp, best), encoding="utf-8", errors="replace") as fh:
                text = vtt_to_text(fh.read())
        title = next((ln for ln in out.splitlines() if ln.strip()), None)
        code = best.rsplit(".", 2)[-2] if best.count(".") >= 2 else None
        return [make_item(title=title, url=url, text=text, raw={"lang": code})]

# -*- coding: utf-8 -*-
"""Stable read/search facade over Agent Reach's platform backends."""

from __future__ import annotations

import glob
import json
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, TypedDict, cast

from agent_reach.channels import get_all_channels, get_channel
from agent_reach.config import Config
from agent_reach.utils.process import utf8_subprocess_env


def _decode_output(text: str) -> Any:
    text = text.strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _run(command: list[str], timeout: int = 60) -> Any:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=utf8_subprocess_env(),
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or f"backend exited with status {result.returncode}")
    return _decode_output(result.stdout)


def _jina_search(query: str) -> str:
    search_url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    url = "https://r.jina.ai/" + search_url
    request = urllib.request.Request(
        url,
        headers={"Accept": "text/plain", "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


class AccessRouter:
    """Choose a healthy channel backend and execute a read-only operation."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config(read_only=True)

    def search(self, query: str, *, limit: int = 5) -> dict:
        expression = f"exa.web_search_exa(query: {json.dumps(query)}, numResults: {limit})"
        exa = get_channel("exa_search")
        if exa is not None:
            status, _ = exa.check(self.config)
            if status == "ok":
                try:
                    content = _run(["mcporter", "call", expression])
                    return {
                        "platform": "exa_search",
                        "backend": "Exa via mcporter",
                        "content": content,
                    }
                except (FileNotFoundError, RuntimeError):
                    pass
        return {
            "platform": "web_search",
            "backend": "DuckDuckGo via Jina Reader",
            "content": _jina_search(query),
            "limitations": [
                "Exa via mcporter unavailable; used DuckDuckGo via Jina Reader"
            ],
        }

    def read(self, url: str) -> dict:
        channel = next(ch for ch in get_all_channels() if ch.can_handle(url))
        status, reason = channel.check(self.config)
        backend = channel.active_backend
        if status == "error" or backend is None:
            raise RuntimeError(reason)

        command = channel.read_command(url)
        if command is not None:
            content = _run(command)
        elif channel.name == "web":
            content = cast(Any, channel).read(url)
        else:
            from agent_reach.channels.web import WebChannel

            content = WebChannel().read(url)
            backend = "Jina Reader fallback"

        return {"platform": channel.name, "backend": backend, "content": content}

    def extract(self, url: str) -> dict:
        """Extract consumable content; for YouTube this means subtitle text."""
        channel = next(ch for ch in get_all_channels() if ch.can_handle(url))
        if channel.name != "youtube":
            return self.read(url)

        status, reason = channel.check(self.config)
        if status == "error" or channel.active_backend is None:
            raise RuntimeError(reason)
        with tempfile.TemporaryDirectory(prefix="agent-reach-youtube-") as temp_dir:
            output = f"{temp_dir}/%(id)s"
            _run(
                [
                    sys.executable, "-m", "yt_dlp", "--write-sub", "--write-auto-sub",
                    "--sub-langs", "en,en-US,en-GB",
                    "--sub-format", "vtt", "--skip-download", "-o", output, url,
                ],
                timeout=120,
            )
            subtitle_paths = sorted(glob.glob(f"{temp_dir}/*.vtt"))
            if not subtitle_paths:
                raise RuntimeError("no subtitles were available for this YouTube video")
            transcript = "\n".join(
                _clean_vtt(path) for path in subtitle_paths
            )
        return {
            "platform": "youtube",
            "backend": channel.active_backend,
            "content": transcript,
        }


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


class NormalizedResult(TypedDict):
    status: str
    platform: str | None
    backend: str | None
    source_url: str | None
    query: str | None
    content: Any
    author: Any
    published_at: Any
    replies: list[Any]
    media: list[Any]
    limitations: list[str]
    retrieved_at: str


def normalize_result(
    raw: dict,
    *,
    source_url: str | None = None,
    query: str | None = None,
    status: str = "success",
    limitations: list[str] | None = None,
) -> NormalizedResult:
    """Return the common machine-readable envelope for every backend."""
    payload = raw.get("content")
    metadata = payload if isinstance(payload, dict) else {}
    normalized_content = payload
    for key in ("full_text", "text", "body", "description"):
        if metadata.get(key) is not None:
            normalized_content = metadata[key]
            break
    replies = raw.get("replies", metadata.get("replies") or metadata.get("comments") or [])
    media = raw.get("media", metadata.get("media") or metadata.get("attachments") or [])
    result: NormalizedResult = {
        "status": status,
        "platform": raw.get("platform"),
        "backend": raw.get("backend"),
        "source_url": source_url,
        "query": query,
        "content": normalized_content,
        "author": raw.get("author", metadata.get("author") or metadata.get("user")),
        "published_at": raw.get(
            "published_at", metadata.get("published_at") or metadata.get("created_at")
        ),
        "replies": replies if isinstance(replies, list) else [],
        "media": media if isinstance(media, list) else [],
        "limitations": limitations or raw.get("limitations", []),
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return result

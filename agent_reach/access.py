# -*- coding: utf-8 -*-
"""Stable read/search facade over Agent Reach's platform backends."""

from __future__ import annotations

import json
import subprocess
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
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
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
        channel, backend = self._ready_channel(url)
        return self._read_ready(channel, backend, url)

    def _read_ready(self, channel, backend: str, url: str) -> dict:
        """Read through an already-probed channel, falling back after runtime failure."""

        command = channel.read_command(url)
        if command is not None:
            try:
                content = _run(command)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                from agent_reach.channels.web import WebChannel

                content = WebChannel().read(url)
                backend = "Jina Reader fallback"
        elif channel.name == "web":
            content = cast(Any, channel).read(url)
        else:
            from agent_reach.channels.web import WebChannel

            content = WebChannel().read(url)
            backend = "Jina Reader fallback"

        return {"platform": channel.name, "backend": backend, "content": content}

    def extract(self, url: str) -> dict:
        """Extract consumable platform content through the channel capability."""
        channel, backend = self._ready_channel(url)
        try:
            extracted = channel.extract_content(url, _run)
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            return self._read_ready(channel, backend, url)
        if extracted is None:
            return self._read_ready(channel, backend, url)
        return {**extracted, "platform": channel.name, "backend": backend}

    def _ready_channel(self, url: str):
        channel = next(ch for ch in get_all_channels() if ch.can_handle(url))
        status, reason = channel.check(self.config)
        if status == "error" or channel.active_backend is None:
            raise RuntimeError(reason)
        return channel, channel.active_backend


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
            "published_at",
            metadata.get("published_at") or metadata.get("created_at") or metadata.get("createdAt"),
        ),
        "replies": replies if isinstance(replies, list) else [],
        "media": media if isinstance(media, list) else [],
        "limitations": limitations or raw.get("limitations", []),
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return result

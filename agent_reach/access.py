# -*- coding: utf-8 -*-
"""Stable read/search facade over Agent Reach's platform backends."""

from __future__ import annotations

import json
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, cast

from agent_reach.channels import get_all_channels
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
        try:
            content = _run(["mcporter", "call", expression])
            return {
                "platform": "exa_search",
                "backend": "Exa via mcporter",
                "content": content,
            }
        except (FileNotFoundError, RuntimeError):
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

        if channel.name == "web":
            content = cast(Any, channel).read(url)
        elif channel.name == "youtube":
            content = _run(["yt-dlp", "--dump-single-json", "--skip-download", url])
        elif channel.name == "twitter" and backend == "twitter-cli":
            content = _run(["twitter", "tweet", url, "--json"])
        elif channel.name == "github":
            content = _run(["gh", "repo", "view", url, "--json", "nameWithOwner,description,url"])
        elif channel.name == "bilibili" and backend == "bili-cli":
            content = _run(["bili", "video", url])
        elif backend == "OpenCLI":
            action = "note" if channel.name == "xiaohongshu" else "read"
            content = _run(["opencli", channel.name, action, url, "-f", "json"])
        elif channel.name == "reddit" and backend == "rdt-cli":
            content = _run(["rdt", "read", url, "--json"])
        else:
            # Jina remains the documented universal, read-only fallback.
            from agent_reach.channels.web import WebChannel

            content = WebChannel().read(url)
            backend = "Jina Reader fallback"

        return {"platform": channel.name, "backend": backend, "content": content}


def normalize_result(
    raw: dict,
    *,
    source_url: str | None = None,
    query: str | None = None,
    status: str = "success",
    limitations: list[str] | None = None,
) -> dict:
    """Return the common machine-readable envelope for every backend."""
    result = {
        "status": status,
        "platform": raw.get("platform"),
        "backend": raw.get("backend"),
        "source_url": source_url,
        "query": query,
        "content": raw.get("content"),
        "author": raw.get("author"),
        "published_at": raw.get("published_at"),
        "replies": raw.get("replies", []),
        "media": raw.get("media", []),
        "limitations": limitations or raw.get("limitations", []),
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return result

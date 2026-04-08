# -*- coding: utf-8 -*-
"""Twitter/X channel checks."""

from __future__ import annotations

import shutil
import subprocess

from agent_reach.utils.commands import find_command

from .base import Channel


class TwitterChannel(Channel):
    name = "twitter"
    description = "Twitter/X search and timeline access"
    backends = ["twitter-cli"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        host = urlparse(url).netloc.lower()
        return "x.com" in host or "twitter.com" in host

    def check(self, config=None):
        twitter = find_command("twitter") or shutil.which("twitter")
        if not twitter:
            return "warn", "twitter-cli is missing. Install it with uv tool install twitter-cli"

        try:
            result = subprocess.run(
                [twitter, "status"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except Exception:
            return "warn", "twitter-cli is installed but status could not be checked"

        output = f"{result.stdout}\n{result.stderr}".lower()
        if result.returncode == 0 and "ok: true" in output:
            return "ok", "Ready for tweet reads, search, and timeline lookups"
        if "not_authenticated" in output:
            return "warn", (
                "twitter-cli is installed but not authenticated. "
                "Run agent-reach configure twitter-cookies \"auth_token=...; ct0=...\""
            )
        return "warn", "twitter-cli is installed but did not report a healthy session"

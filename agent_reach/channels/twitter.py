# -*- coding: utf-8 -*-
"""Twitter/X — check if twitter-cli or bird CLI is available."""

import shutil
import subprocess
from .base import Channel


class TwitterChannel(Channel):
    name = "twitter"
    description = "Twitter/X posts"
    backends = ["twitter-cli", "bird CLI (legacy)"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "x.com" in d or "twitter.com" in d

    def check(self, config=None):
        # Prefer twitter-cli, fallback to bird/birdx
        twitter = shutil.which("twitter")
        bird = shutil.which("bird") or shutil.which("birdx")

        if twitter:
            return self._check_twitter_cli(twitter)
        elif bird:
            return self._check_bird(bird)
        else:
            return "warn", (
                "Twitter CLI not installed. Install with:\n"
                "  pipx install twitter-cli\n"
                "or:\n"
                "  uv tool install twitter-cli"
            )

    def _check_twitter_cli(self, binary: str):
        try:
            r = subprocess.run(
                [binary, "status"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=10
            )
            output = (r.stdout or "") + (r.stderr or "")
            if r.returncode == 0 and "ok: true" in output:
                return "ok", (
                    "twitter-cli fully available (search, read posts, timeline, long-form/Article, "
                    "user lookup, Thread)"
                )
            if "not_authenticated" in output:
                return "warn", (
                    "twitter-cli installed but not authenticated. Set up with:\n"
                    "  export TWITTER_AUTH_TOKEN=\"xxx\"\n"
                    "  export TWITTER_CT0=\"yyy\"\n"
                    "or make sure you are logged into x.com in your browser"
                )
            return "warn", (
                "twitter-cli installed but authentication check failed. Run:\n"
                "  twitter -v status for details"
            )
        except Exception:
            return "warn", "twitter-cli installed but connection failed"

    def _check_bird(self, binary: str):
        try:
            r = subprocess.run(
                [binary, "check"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=10
            )
            output = (r.stdout or "") + (r.stderr or "")
            if r.returncode == 0:
                return "ok", "bird CLI available (read, search posts, including long-form/X Article)"
            if "Missing credentials" in output or "missing" in output.lower():
                return "warn", (
                    "bird CLI installed but authentication not configured. Set environment variables:\n"
                    "  export AUTH_TOKEN=\"xxx\"\n"
                    "  export CT0=\"yyy\""
                )
            return "warn", (
                "bird CLI installed but authentication check failed."
            )
        except Exception:
            return "warn", "bird CLI installed but connection failed"

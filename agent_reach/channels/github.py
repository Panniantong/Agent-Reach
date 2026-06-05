# -*- coding: utf-8 -*-
"""GitHub — check if gh CLI is available."""

import shutil
import subprocess
from .base import Channel


class GitHubChannel(Channel):
    name = "github"
    description = "GitHub repositories and code"
    backends = ["gh CLI"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        return "github.com" in urlparse(url).netloc.lower()

    def check(self, config=None):
        gh = shutil.which("gh")
        if not gh:
            return "warn", "gh CLI not installed. Install: https://cli.github.com"
        try:
            r = subprocess.run(
                [gh, "auth", "status"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=5
            )
            if r.returncode == 0:
                return "ok", "Fully available (read, search, fork, issues, PRs, etc.)"
            return "warn", "gh CLI installed but not authenticated. Run gh auth login to unlock full functionality"
        except Exception:
            return "warn", "gh CLI status check failed; run gh auth status to view details"

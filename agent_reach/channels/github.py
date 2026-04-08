# -*- coding: utf-8 -*-
"""GitHub channel health checks."""

from __future__ import annotations

import os
from pathlib import Path

from agent_reach.utils.commands import find_command

from .base import Channel


class GitHubChannel(Channel):
    name = "github"
    description = "GitHub repositories and code search"
    backends = ["gh CLI"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        return "github.com" in urlparse(url).netloc.lower()

    def check(self, config=None):
        gh = find_command("gh")
        if not gh:
            return "warn", "gh CLI is missing. Install it with winget install --id GitHub.cli -e"

        if _has_gh_auth_material():
            return "ok", "Ready for repo view, code search, issues, PRs, and forks"
        return "warn", "gh CLI is installed but not authenticated. Run gh auth login"


def _has_gh_auth_material() -> bool:
    appdata = os.environ.get("APPDATA", "")
    candidates = [
        Path(appdata) / "GitHub CLI" / "hosts.yml",
        Path.home() / ".config" / "gh" / "hosts.yml",
    ]
    return any(candidate.exists() and candidate.stat().st_size > 0 for candidate in candidates)

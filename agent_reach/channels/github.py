# -*- coding: utf-8 -*-
"""GitHub channel health checks."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from agent_reach.utils.commands import find_command

from .base import Channel


class GitHubChannel(Channel):
    name = "github"
    description = "GitHub repositories and code search"
    backends = ["gh CLI"]
    tier = 0
    auth_kind = "token"
    entrypoint_kind = "cli"
    operations = ["search", "read"]
    operation_inputs = {
        "search": "query",
        "read": "repository",
    }
    operation_options = {
        "search": [
            {
                "name": "page_size",
                "type": "integer",
                "required": False,
                "minimum": 1,
                "cli_flag": "--page-size",
                "sdk_kwarg": "page_size",
                "description": "Maximum repositories requested from GitHub per API page.",
            },
            {
                "name": "max_pages",
                "type": "integer",
                "required": False,
                "minimum": 1,
                "cli_flag": "--max-pages",
                "sdk_kwarg": "max_pages",
                "description": "Maximum GitHub API pages to request before stopping with pagination metadata.",
            },
            {
                "name": "page",
                "type": "integer",
                "required": False,
                "minimum": 1,
                "cli_flag": "--page",
                "sdk_kwarg": "page",
                "description": "Starting GitHub search page number.",
            },
        ]
    }
    required_commands = ["gh"]
    host_patterns = ["https://github.com/*", "https://api.github.com/*"]
    example_invocations = [
        'agent-reach collect --channel github --operation read --input "openai/openai-python" --json',
        'agent-reach collect --channel github --operation search --input "agent reach" --limit 10 --json',
    ]
    supports_probe = True
    install_hints = [
        "Install gh with winget and authenticate with gh auth login.",
        "You can also store a token with agent-reach configure github-token <TOKEN>.",
    ]

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        return "github.com" in urlparse(url).netloc.lower()

    def check(self, config=None):
        gh = find_command("gh")
        if not gh:
            return "warn", "gh CLI is missing. Install it with winget install --id GitHub.cli -e"

        if _has_gh_auth_material(config):
            return "ok", "Ready for repo view, code search, issues, PRs, and forks"
        return "warn", "gh CLI is installed but not authenticated. Run gh auth login"

    def probe(self, config=None):
        gh = find_command("gh")
        if not gh:
            return "warn", "gh CLI is missing. Install it with winget install --id GitHub.cli -e"

        try:
            result = subprocess.run(
                [gh, "auth", "status"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                env=_github_runtime_env(config),
            )
        except Exception as exc:
            return "warn", f"gh auth status failed: {exc}"

        output = f"{result.stdout}\n{result.stderr}".lower()
        if result.returncode == 0:
            return "ok", "gh auth status completed successfully"
        if "not logged into any hosts" in output or "authentication failed" in output:
            return "warn", "gh CLI is installed but not authenticated. Run gh auth login"
        return "warn", "gh auth status did not complete cleanly"


def _github_runtime_env(config=None) -> dict[str, str]:
    env = os.environ.copy()
    token = env.get("GITHUB_TOKEN") or env.get("GH_TOKEN")
    if not token and config is not None:
        token = config.get("github_token")
    if token:
        env["GITHUB_TOKEN"] = str(token)
        env["GH_TOKEN"] = str(token)
    return env


def _has_gh_auth_material(config=None) -> bool:
    if _github_runtime_env(config).get("GITHUB_TOKEN"):
        return True

    appdata = os.environ.get("APPDATA", "")
    candidates = [
        Path(appdata) / "GitHub CLI" / "hosts.yml",
        Path.home() / ".config" / "gh" / "hosts.yml",
    ]
    return any(candidate.exists() and candidate.stat().st_size > 0 for candidate in candidates)

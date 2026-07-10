# -*- coding: utf-8 -*-
"""GitHub — check if gh CLI is available."""

from agent_reach.probe import probe_command

from .base import Channel


class GitHubChannel(Channel):
    name = "github"
    description = "GitHub repos and code"
    backends = ["gh CLI"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        return "github.com" in urlparse(url).netloc.lower()

    def check(self, config=None):
        # Actually run gh auth status as a live probe. Note: rc!=0 when not logged in is a normal business state (warn), not an error.
        probe = probe_command("gh", ["auth", "status"], timeout=10, package="gh")
        if probe.status == "missing":
            self.active_backend = None
            return "warn", "gh CLI not installed. Install: https://cli.github.com"
        if probe.status == "broken":
            # gh is installed as a binary (brew/official package), not a pip package — hint doesn't use pipx/uv wording
            self.active_backend = None
            return "error", (
                "gh command exists but cannot execute — the install is broken. Reinstalling fixes it:\n"
                "  brew reinstall gh\n"
                "or reinstall gh CLI from https://cli.github.com"
            )
        if probe.status == "timeout":
            # gh itself can start (the tool is alive), just the status check timed out
            self.active_backend = "gh CLI"
            return "warn", "gh CLI status check timed out; run gh auth status for details"
        if probe.ok:
            self.active_backend = "gh CLI"
            return "ok", "Fully available (read, search, fork, issues, PRs, etc.)"
        # rc != 0: gh is alive but not authenticated (gh auth status's normal business state)
        self.active_backend = "gh CLI"
        return "warn", "gh CLI is installed but not authenticated. Run gh auth login to unlock full functionality"

# -*- coding: utf-8 -*-
"""GitHub — check if gh CLI is available."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from agent_reach.probe import probe_command
from agent_reach.utils.paths import (
    PrivatePathError,
    read_small_text_no_follow,
)

from .base import Channel

_MAX_HOSTS_BYTES = 1024 * 1024
_GH_READ_ONLY_ENV = {
    # gh 2.92 creates ~/.local/state/gh/device-id even for `--version` unless
    # telemetry is disabled. These are documented gh environment controls.
    "GH_TELEMETRY": "false",
    "DO_NOT_TRACK": "true",
    "GH_NO_UPDATE_NOTIFIER": "1",
    "GH_NO_EXTENSION_UPDATE_NOTIFIER": "1",
}


class GitHubConfigError(ValueError):
    """Raised when gh credential metadata cannot be read safely."""


def _gh_hosts_path() -> Path:
    override = os.environ.get("GH_CONFIG_DIR")
    if override:
        return Path(os.path.abspath(os.path.expanduser(override))) / "hosts.yml"

    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "gh" / "hosts.yml"

    if os.name == "nt":
        app_data = os.environ.get("APPDATA")
        if app_data:
            return Path(app_data) / "GitHub CLI" / "hosts.yml"

    return Path.home() / ".config" / "gh" / "hosts.yml"


def _saved_github_host_configured() -> bool:
    """Inspect github.com's hosts.yml entry without executing gh."""
    hosts_path = _gh_hosts_path()
    try:
        raw = read_small_text_no_follow(
            hosts_path,
            max_bytes=_MAX_HOSTS_BYTES,
        )
    except (OSError, PrivatePathError, UnicodeError) as exc:
        raise GitHubConfigError("gh hosts.yml could not be read safely") from exc
    if raw is None:
        return False
    try:
        payload = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise GitHubConfigError("gh hosts.yml is not valid UTF-8 YAML") from exc
    if payload is None:
        return False
    if not isinstance(payload, dict):
        raise GitHubConfigError("gh hosts.yml top level must be an object")

    host = payload.get("github.com")
    if host is None:
        return False
    if not isinstance(host, dict):
        raise GitHubConfigError("gh hosts.yml has an invalid github.com configuration")

    users = host.get("users")
    if users is not None and not isinstance(users, dict):
        raise GitHubConfigError("gh hosts.yml has an invalid users configuration")
    return bool(host.get("oauth_token") or host.get("user") or users)


def _explicit_github_credentials(config) -> bool:
    if any(os.environ.get(name) for name in ("GH_TOKEN", "GITHUB_TOKEN")):
        return True
    if config is None:
        return False
    try:
        return bool(config.get("github_token"))
    except Exception as exc:
        raise GitHubConfigError("Agent Reach GitHub configuration could not be read") from exc


class GitHubChannel(Channel):
    name = "github"
    description = "GitHub repositories and code"
    backends = ["gh CLI"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "github.com")

    def check(self, config=None):
        self.active_backend = None
        probe = probe_command(
            "gh",
            ["--version"],
            timeout=10,
            package="gh",
            env=_GH_READ_ONLY_ENV,
        )
        if probe.status == "missing":
            return "warn", "gh CLI is not installed. Install: https://cli.github.com"
        if probe.status == "broken":
            return "error", (
                "The gh command exists but cannot execute—the installation is broken. Reinstall to fix it:\n"
                "  brew reinstall gh\n"
                "Or reinstall gh CLI from https://cli.github.com"
            )
        if not probe.ok:
            detail = probe.hint or probe.status
            return "error", f"gh CLI version check failed: {detail}"

        try:
            configured = _explicit_github_credentials(
                config
            ) or _saved_github_host_configured()
        except GitHubConfigError as exc:
            return "warn", (
                f"gh CLI is executable, but authentication configuration could not be checked safely: {exc}。"
                "Doctor does not run `gh auth status` because it may write a device ID, so authentication was not verified live."
            )

        if configured:
            return "warn", (
                "gh CLI is executable and explicit authentication configuration was detected; Doctor does not run "
                "`gh auth status` because it may write a device ID, so it was not verified live and is not marked available."
            )
        return "warn", (
            "gh CLI is executable, but no explicit authentication configuration was detected. Run `gh auth login` "
            "to authenticate; Doctor will not automatically run `gh auth status`."
        )

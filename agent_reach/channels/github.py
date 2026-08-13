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
        raise GitHubConfigError("gh hosts.yml 无法安全读取") from exc
    if raw is None:
        return False
    try:
        payload = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise GitHubConfigError("gh hosts.yml 不是有效的 UTF-8 YAML") from exc
    if payload is None:
        return False
    if not isinstance(payload, dict):
        raise GitHubConfigError("gh hosts.yml 顶层必须是对象")

    host = payload.get("github.com")
    if host is None:
        return False
    if not isinstance(host, dict):
        raise GitHubConfigError("gh hosts.yml 的 github.com 配置无效")

    users = host.get("users")
    if users is not None and not isinstance(users, dict):
        raise GitHubConfigError("gh hosts.yml 的 users 配置无效")
    return bool(host.get("oauth_token") or host.get("user") or users)


def _explicit_github_credentials(config) -> bool:
    if any(os.environ.get(name) for name in ("GH_TOKEN", "GITHUB_TOKEN")):
        return True
    if config is None:
        return False
    try:
        return bool(config.get("github_token"))
    except Exception as exc:
        raise GitHubConfigError("Agent Reach 的 GitHub 配置无法读取") from exc


class GitHubChannel(Channel):
    name = "github"
    description = "GitHub 仓库和代码"
    backends = ["gh CLI"]
    tier = 0
    reference = "dev"
    url_commands = {"gh CLI": 'gh repo view "{url}"'}

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
            return "warn", "gh CLI 未安装。安装：https://cli.github.com"
        if probe.status == "broken":
            return "error", (
                "gh 命令存在但无法执行——安装已损坏。重装即可修复：\n"
                "  brew reinstall gh\n"
                "或从 https://cli.github.com 重新安装 gh CLI"
            )
        if not probe.ok:
            detail = probe.hint or probe.status
            return "error", f"gh CLI 版本检查失败：{detail}"

        try:
            configured = _explicit_github_credentials(
                config
            ) or _saved_github_host_configured()
        except GitHubConfigError as exc:
            return "warn", (
                f"gh CLI 可执行，但认证配置无法安全确认：{exc}。"
                "Doctor 不执行会写 device-id 的 `gh auth status`，当前未验证。"
            )

        if configured:
            return "warn", (
                "gh CLI 可执行，且检测到显式认证配置；Doctor 不执行会写"
                " device-id 的 `gh auth status`，因此未实时验证，未标记为可用。"
            )
        return "warn", (
            "gh CLI 可执行，但未检测到显式认证配置。运行 `gh auth login` "
            "完成登录；Doctor 不会自动执行 `gh auth status`。"
        )

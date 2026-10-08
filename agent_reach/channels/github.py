# -*- coding: utf-8 -*-
"""GitHub — check if gh CLI is available."""

from __future__ import annotations

import json
import os
import re
import urllib.error
from pathlib import Path
from urllib.parse import urlencode

import yaml

from agent_reach.probe import probe_command
from agent_reach.runtime.result import (
    BAD_INPUT,
    NEED_LOGIN,
    NOT_FOUND,
    RATE_LIMITED,
    ReachError,
    make_item,
)
from agent_reach.runtime.run import CommandFailed, http_request, run_cmd
from agent_reach.utils.paths import (
    PrivatePathError,
    read_small_text_no_follow,
)

from .base import Action, Channel, Param

_API = "https://api.github.com"
_TARGET_RE = re.compile(
    r"^(?:https?://(?:www\.)?github\.com/)?([\w.-]+)/([\w.-]+?)(?:\.git)?"
    r"(?:/(?:issues|pull)/(\d+))?/?(?:[?#].*)?$"
)
_README_MAX_CHARS = 50_000

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


def _parse_target(target: str):
    """owner/repo, a repo link, or an issue/PR link → (owner, repo, number|None)."""
    m = _TARGET_RE.match(str(target).strip())
    if not m:
        raise ReachError(BAD_INPUT, "target must be owner/repo or a github.com repo/issue/PR link")
    owner, repo, number = m.groups()
    return owner, repo, int(number) if number else None


def _gh_get(path: str, timeout: float, accept: str = "application/vnd.github+json") -> bytes:
    try:
        out = run_cmd(
            ["gh", "api", "-H", f"Accept: {accept}", path],
            timeout=timeout,
            env=_GH_READ_ONLY_ENV,
        )
    except CommandFailed as exc:
        err = exc.stderr.lower()
        if "http 404" in err or "not found" in err:
            raise ReachError(NOT_FOUND, exc.message) from None
        if "gh auth login" in err or "authentication" in err:
            raise ReachError(NEED_LOGIN, "gh is not logged in") from None
        if "rate limit" in err:
            raise ReachError(RATE_LIMITED, exc.message) from None
        raise
    return out.encode("utf-8")


def _api_get(path: str, timeout: float, accept: str = "application/vnd.github+json") -> bytes:
    headers = {"Accept": accept, "User-Agent": "agent-reach"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        return http_request(f"{_API}{path}", timeout=timeout, headers=headers)
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise ReachError(RATE_LIMITED, "GitHub API rate limit (60/hour without a token)") from None
        raise


def _repo_item(repo: dict, readme: str | None = None) -> dict:
    return make_item(
        title=repo.get("full_name"),
        url=repo.get("html_url"),
        author=(repo.get("owner") or {}).get("login"),
        published_at=repo.get("created_at"),
        text=readme or repo.get("description"),
        raw={
            k: repo.get(k)
            for k in ("description", "stargazers_count", "forks_count", "language",
                      "topics", "pushed_at", "open_issues_count", "archived")
        }
        | {"license": (repo.get("license") or {}).get("spdx_id")},
    )


class GitHubChannel(Channel):
    name = "github"
    description = "GitHub 仓库和代码"
    backends = ["gh CLI"]
    tier = 0

    level = "default"
    actions = (
        Action(
            "search",
            "Search repositories",
            (
                Param("query", "what to search for"),
                Param("limit", "max results", required=False, type=int, default=5),
            ),
            (("gh", "_gh_search"), ("github-api", "_api_search")),
            live_test={"query": "yt-dlp", "limit": 2},
        ),
        Action(
            "read",
            "Read a repository (with README) or an issue / PR (with comments)",
            (Param("target", "owner/repo, or a repo / issue / PR link"),),
            (("gh", "_gh_read"), ("github-api", "_api_read")),
            live_test={"target": "yt-dlp/yt-dlp"},
        ),
    )

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

    # ── unified entry backends ──

    @staticmethod
    def _search(get, query: str, limit: int, timeout: float) -> list:
        path = "/search/repositories?" + urlencode({"q": query, "per_page": limit})
        data = json.loads(get(path, timeout))
        return [_repo_item(r) for r in data.get("items", [])[:limit]]

    @staticmethod
    def _read(get, target: str, timeout: float) -> list:
        owner, repo, number = _parse_target(target)
        if number is None:
            info = json.loads(get(f"/repos/{owner}/{repo}", timeout / 2))
            try:
                readme = get(f"/repos/{owner}/{repo}/readme", timeout / 2, "application/vnd.github.raw")
                readme_text = readme.decode("utf-8", errors="replace")[:_README_MAX_CHARS]
            except ReachError as exc:
                if exc.code != NOT_FOUND:
                    raise
                readme_text = None
            return [_repo_item(info, readme_text)]
        issue = json.loads(get(f"/repos/{owner}/{repo}/issues/{number}", timeout / 2))
        comments = json.loads(get(f"/repos/{owner}/{repo}/issues/{number}/comments?per_page=50", timeout / 2))
        parts = [issue.get("body") or ""]
        for c in comments:
            parts.append(f"\n@{(c.get('user') or {}).get('login', '')}: {c.get('body') or ''}")
        return [
            make_item(
                title=issue.get("title"),
                url=issue.get("html_url"),
                author=(issue.get("user") or {}).get("login"),
                published_at=issue.get("created_at"),
                text="\n".join(parts).strip(),
                raw={
                    "state": issue.get("state"),
                    "labels": [lb.get("name") for lb in issue.get("labels", [])],
                    "comments": issue.get("comments"),
                    "is_pull_request": "pull_request" in issue,
                },
            )
        ]

    def _gh_search(self, *, query: str, limit: int, timeout: float) -> list:
        return self._search(_gh_get, query, limit, timeout)

    def _api_search(self, *, query: str, limit: int, timeout: float) -> list:
        return self._search(_api_get, query, limit, timeout)

    def _gh_read(self, *, target: str, timeout: float) -> list:
        return self._read(_gh_get, target, timeout)

    def _api_read(self, *, target: str, timeout: float) -> list:
        return self._read(_api_get, target, timeout)

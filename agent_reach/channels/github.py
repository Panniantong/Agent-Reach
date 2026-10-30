# -*- coding: utf-8 -*-
"""GitHub — repositories, issues and PRs via gh CLI, falling back to the REST API."""

from __future__ import annotations

import json
import os
import re
import urllib.error
from urllib.parse import urlencode

from agent_reach.runtime.result import (
    BAD_INPUT,
    NEED_SETUP,
    NOT_FOUND,
    RATE_LIMITED,
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
)
from agent_reach.runtime.run import CommandFailed, http_request, run_cmd

from .base import Action, Channel, Param

_API = "https://api.github.com"
_TARGET_RE = re.compile(
    r"^(?:https?://(?:www\.)?github\.com/)?([\w.-]+)/([\w.-]+?)(?:\.git)?"
    r"(?:/(?:issues|pull)/(\d+))?/?(?:[?#].*)?$"
)
_README_MAX_CHARS = 50_000

_GH_READ_ONLY_ENV = {
    # gh 2.92 creates ~/.local/state/gh/device-id even for `--version` unless
    # telemetry is disabled. These are documented gh environment controls.
    "GH_TELEMETRY": "false",
    "DO_NOT_TRACK": "true",
    "GH_NO_UPDATE_NOTIFIER": "1",
    "GH_NO_EXTENSION_UPDATE_NOTIFIER": "1",
}


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
            raise ReachError(NEED_SETUP, "gh has no usable credentials; try the public GitHub API") from None
        if "rate limit" in err:
            raise ReachError(RATE_LIMITED, exc.message) from None
        raise
    return out.encode("utf-8")


def _api_get(path: str, timeout: float, accept: str = "application/vnd.github+json") -> bytes:
    headers = {"Accept": accept, "User-Agent": "agent-reach"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        from agent_reach.config import Config

        token = Config(read_only=True).get("github_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        return http_request(f"{_API}{path}", timeout=timeout, headers=headers)
    except urllib.error.HTTPError as exc:
        if exc.code == 429 or (exc.code == 403 and (
            exc.headers.get("X-RateLimit-Remaining") == "0" or exc.headers.get("Retry-After")
        )):
            raise ReachError(RATE_LIMITED, "GitHub API rate limit (60/hour without a token)") from None
        if exc.code == 403:
            raise ReachError(UPSTREAM_BROKEN, "GitHub API denied this request (HTTP 403); no rate-limit evidence") from None
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

import json
from unittest.mock import Mock

import pytest

from agent_reach.channels import github
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.run import CommandFailed


def test_gh_429_is_rate_limited_without_api_fallback(monkeypatch):
    def rate_limited(*args, **kwargs):
        raise CommandFailed(
            "UPSTREAM_BROKEN",
            "gh exited 1: HTTP 429: Too Many Requests",
            stderr="gh: HTTP 429: Too Many Requests",
        )

    monkeypatch.setattr(github, "run_cmd", rate_limited)
    api = Mock(side_effect=AssertionError("a platform rate limit must not fall back"))
    monkeypatch.setattr(github, "http_request", api)

    out = run_action(github.GitHubChannel(), "search", {"query": "agent", "limit": 1})

    assert out["ok"] is False
    assert out["error"]["code"] == "RATE_LIMITED"
    assert [attempt["result"] for attempt in out["meta"]["attempts"]] == ["RATE_LIMITED"]
    api.assert_not_called()


@pytest.mark.parametrize(
    ("stderr", "code"),
    [
        ("gh: Not Found (HTTP 404)", "NOT_FOUND"),
        ("gh: HTTP 500: Internal Server Error", "UPSTREAM_BROKEN"),
    ],
)
def test_gh_non_rate_limit_failures_keep_their_codes(monkeypatch, stderr, code):
    def failed(*args, **kwargs):
        raise CommandFailed("UPSTREAM_BROKEN", "gh exited 1", stderr=stderr)

    monkeypatch.setattr(github, "run_cmd", failed)

    out = run_action(
        github.GitHubChannel(), "search", {"query": "agent", "limit": 1}, only_backend="gh"
    )

    assert out["ok"] is False
    assert out["error"]["code"] == code


def test_gh_search_success_still_normalizes_items(monkeypatch):
    repository = {
        "full_name": "owner/repo",
        "html_url": "https://github.com/owner/repo",
        "owner": {"login": "owner"},
        "description": "Example repository",
    }
    monkeypatch.setattr(
        github, "run_cmd", lambda *args, **kwargs: json.dumps({"items": [repository]})
    )

    out = run_action(
        github.GitHubChannel(), "search", {"query": "agent", "limit": 1}, only_backend="gh"
    )

    assert out["ok"] is True
    assert out["backend"] == "gh"
    assert out["items"][0]["title"] == "owner/repo"
    assert out["items"][0]["author"] == "owner"
    assert out["items"][0]["text"] == "Example repository"

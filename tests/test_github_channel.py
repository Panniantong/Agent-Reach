import json
import urllib.error
from unittest.mock import Mock

import pytest

from agent_reach.channels import github
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.run import CommandFailed


def _search_with_failure(monkeypatch, backend, failure):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    boundary = "run_cmd" if backend == "gh" else "http_request"
    monkeypatch.setattr(github, boundary, Mock(side_effect=failure))
    return run_action(
        github.GitHubChannel(),
        "search",
        {"query": "repo", "limit": 1},
        only_backend=backend,
    )


@pytest.mark.parametrize(
    ("backend", "failure"),
    [
        (
            "gh",
            CommandFailed(
                "UPSTREAM_BROKEN",
                "gh exited",
                stderr="gh: Bad credentials (HTTP 401)",
            ),
        ),
        (
            "github-api",
            urllib.error.HTTPError(
                "https://api.github.com/search/repositories", 401, "Unauthorized", {}, None
            ),
        ),
    ],
)
def test_rejected_credentials_request_setup(monkeypatch, backend, failure):
    result = _search_with_failure(monkeypatch, backend, failure)

    assert result["ok"] is False
    assert result["error"]["code"] == "NEED_SETUP"
    assert result["items"] == []


@pytest.mark.parametrize(
    ("backend", "failure"),
    [
        (
            "gh",
            CommandFailed(
                "UPSTREAM_BROKEN",
                "gh exited",
                stderr="gh: server error (HTTP 500)",
            ),
        ),
        (
            "github-api",
            urllib.error.HTTPError(
                "https://api.github.com/search/repositories", 500, "Server Error", {}, None
            ),
        ),
    ],
)
def test_server_failures_stay_upstream_broken(monkeypatch, backend, failure):
    result = _search_with_failure(monkeypatch, backend, failure)

    assert result["ok"] is False
    assert result["error"]["code"] == "UPSTREAM_BROKEN"
    assert result["items"] == []


@pytest.mark.parametrize("backend", ["gh", "github-api"])
def test_successful_search_preserves_normalized_items(monkeypatch, backend):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    payload = json.dumps(
        {"items": [{"full_name": "owner/repo", "html_url": "https://github.com/owner/repo"}]}
    ).encode()
    boundary = "run_cmd" if backend == "gh" else "http_request"
    response = payload.decode() if backend == "gh" else payload
    monkeypatch.setattr(github, boundary, Mock(return_value=response))

    result = run_action(
        github.GitHubChannel(),
        "search",
        {"query": "repo", "limit": 1},
        only_backend=backend,
    )

    assert result["ok"] is True
    assert result["backend"] == backend
    assert result["items"][0]["title"] == "owner/repo"
    assert result["items"][0]["url"] == "https://github.com/owner/repo"

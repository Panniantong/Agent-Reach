import json
from unittest.mock import Mock

import pytest

from agent_reach.channels import github
from agent_reach.runtime.dispatch import run_action


@pytest.mark.parametrize(
    "target",
    [
        "https://github.com/cli/cli",
        "HTTPS://WWW.GITHUB.COM/cli/cli",
    ],
)
def test_read_accepts_case_insensitive_scheme_and_host(target, monkeypatch):
    calls = []

    def fake_http_request(url, **kwargs):
        calls.append(url)
        if url == "https://api.github.com/repos/cli/cli":
            return json.dumps(
                {
                    "full_name": "cli/cli",
                    "html_url": "https://github.com/cli/cli",
                    "owner": {"login": "cli"},
                }
            ).encode()
        if url == "https://api.github.com/repos/cli/cli/readme":
            return b"README"
        raise AssertionError(url)

    monkeypatch.setattr(github, "http_request", fake_http_request)

    result = run_action(
        github.GitHubChannel(),
        "read",
        {"target": target},
        only_backend="github-api",
    )

    assert result["ok"] is True
    assert result["items"][0]["text"] == "README"
    assert calls == [
        "https://api.github.com/repos/cli/cli",
        "https://api.github.com/repos/cli/cli/readme",
    ]


def test_read_keeps_github_path_case_sensitive(monkeypatch):
    request = Mock()
    monkeypatch.setattr(github, "http_request", request)

    result = run_action(
        github.GitHubChannel(),
        "read",
        {"target": "https://github.com/cli/cli/ISSUES/42"},
        only_backend="github-api",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "BAD_INPUT"
    request.assert_not_called()


@pytest.mark.parametrize(
    "target",
    [
        "https://gıthub.com/cli/cli",
        "httpſ://github.com/cli/cli",
    ],
)
def test_read_rejects_non_ascii_case_folding(target, monkeypatch):
    request = Mock()
    monkeypatch.setattr(github, "http_request", request)

    result = run_action(
        github.GitHubChannel(),
        "read",
        {"target": target},
        only_backend="github-api",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "BAD_INPUT"
    request.assert_not_called()

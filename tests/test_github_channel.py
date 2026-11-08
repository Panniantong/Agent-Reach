import json
from urllib.parse import parse_qs, urlparse

from agent_reach.channels import github
from agent_reach.runtime.dispatch import run_action


def test_read_returns_comments_beyond_the_first_page(monkeypatch):
    comments = [
        {"user": {"login": f"user{number}"}, "body": f"comment {number}"}
        for number in range(1, 122)
    ]

    def fake_http_request(url, **kwargs):
        parsed = urlparse(url)
        if parsed.path == "/repos/owner/repo/issues/123":
            payload = {
                "title": "A long discussion",
                "html_url": "https://github.com/owner/repo/issues/123",
                "body": "issue body",
                "user": {"login": "author"},
                "comments": len(comments),
                "labels": [],
            }
        elif parsed.path == "/repos/owner/repo/issues/123/comments":
            query = parse_qs(parsed.query)
            page = int(query.get("page", ["1"])[0])
            per_page = int(query.get("per_page", ["30"])[0])
            start = (page - 1) * per_page
            payload = comments[start : start + per_page]
        else:
            raise AssertionError(f"unexpected request: {url}")
        return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(github, "http_request", fake_http_request)

    result = run_action(
        github.GitHubChannel(),
        "read",
        {"target": "owner/repo/issues/123"},
        only_backend="github-api",
    )

    assert result["ok"]
    text = result["items"][0]["text"]
    comment_lines = [line for line in text.splitlines() if line.startswith("@")]
    assert comment_lines == [
        f"@user{number}: comment {number}" for number in range(1, 122)
    ]

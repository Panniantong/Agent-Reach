"""Regression checks for packaged, read-only comment instructions."""

import shlex
from pathlib import Path

REFERENCES = Path(__file__).resolve().parents[1] / "agent_reach/skill/references"


def test_opencli_comments_use_signed_urls_and_explicit_replies():
    social = (REFERENCES / "social.md").read_text(encoding="utf-8")
    commands = [
        shlex.split(line)
        for line in social.splitlines()
        if line.startswith("opencli xiaohongshu comments ")
    ]
    assert commands
    assert all(args[3] == "NOTE_URL" for args in commands)
    assert any("--with-replies" in args for args in commands)
    assert any("--with-replies" not in args for args in commands)
    assert "xsec_token" in social


def test_comment_body_and_reply_fields_are_backend_specific():
    social = (REFERENCES / "social.md").read_text(encoding="utf-8")
    rows = [line for line in social.splitlines() if line.startswith("| ")]
    opencli = next(line for line in rows if line.startswith("| OpenCLI |"))
    mcp = next(line for line in rows if line.startswith("| xiaohongshu-mcp |"))
    assert all(field in opencli for field in ("`text`", "`is_reply`", "`reply_to`"))
    assert all(field in mcp for field in ("`comments.list`", "`content`", "`subComments`"))
    assert "`text`" not in mcp
    assert "reply_limit" in social
    assert "不是小红书全站评论搜索" in social


def test_github_comment_discovery_and_detail_endpoints_are_distinct():
    dev = (REFERENCES / "dev.md").read_text(encoding="utf-8")
    commands = [shlex.split(line) for line in dev.splitlines() if line.startswith("gh ")]
    search = next(args for args in commands if args[:3] == ["gh", "search", "issues"])
    assert "--include-prs" in search
    assert search[search.index("--match") + 1] == "comments"
    api = [args for args in commands if args[:2] == ["gh", "api"] and "--paginate" in args]
    assert any("repos/OWNER/REPO/issues/NUMBER/comments" in args for args in api)
    assert any("repos/OWNER/REPO/pulls/NUMBER/comments" in args for args in api)
    assert all("html_url" in args[-1] for args in api)

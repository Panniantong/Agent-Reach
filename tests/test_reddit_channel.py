# -*- coding: utf-8 -*-
"""Dedicated tests for Reddit's read-only multi-backend health check."""

from unittest.mock import Mock

import pytest

from agent_reach.channels.reddit import RedditChannel


def test_can_handle_matches_reddit_hosts():
    channel = RedditChannel()
    for url in [
        "https://reddit.com/r/python",
        "https://www.reddit.com/r/python/comments/abc/title/",
        "https://old.reddit.com/r/python",
        "https://redd.it/abc123",
        "HTTPS://REDDIT.COM/r/Python",
    ]:
        assert channel.can_handle(url) is True, url


def test_can_handle_rejects_non_reddit():
    channel = RedditChannel()
    for url in ["https://example.com/r/python", "https://twitter.com/u", ""]:
        assert channel.can_handle(url) is False, url


def test_unconfigured_browser_is_prepared_without_assuming_login(monkeypatch):
    from agent_reach.runtime import browser, session_reuse
    launch = Mock()
    monkeypatch.setattr(browser, "ensure_running", launch)
    monkeypatch.setattr(browser, "connected_contexts", lambda: [])
    monkeypatch.setattr(browser, "bound_context", lambda: None)
    result = session_reuse.prepare("reddit")
    assert launch.call_count == 1 and result["copied_cookies"] == 0
    assert "required_action" not in result and not result.get("blocked")


def test_actual_login_error_is_reported_as_need_login(monkeypatch):
    from agent_reach.channels import reddit
    from agent_reach.runtime.dispatch import run_action
    from agent_reach.runtime.result import NEED_LOGIN, ReachError
    request = Mock(side_effect=ReachError(NEED_LOGIN, "Login wall on the selected browser path"))
    monkeypatch.setattr(reddit, "opencli_call", request)
    result = run_action(RedditChannel(), "search", {"query": "DeepSeek"}, only_backend="opencli")
    assert request.call_count == 1
    assert result["error"]["code"] == NEED_LOGIN


def test_bare_403_is_not_classified_as_login():
    from agent_reach.backends.opencli import _opencli_error
    assert _opencli_error("HTTP 403 Forbidden", "").code != "NEED_LOGIN"


@pytest.mark.parametrize("backend,expected", [(None, "reddit"), ("jina", "web"), ("opencli", "reddit")])
def test_read_url_defaults_to_public_web_and_preserves_explicit_browser(monkeypatch, capsys, backend, expected):
    import json

    from agent_reach.runtime import cli
    def run(ch, action, params, **kwargs):
        return {"ok": True, "channel": ch.name, "items": [], "error": None}
    monkeypatch.setattr(cli, "run_action", run)
    argv = ["read", "https://www.reddit.com/r/DeepSeek/comments/test/"]
    if backend:
        argv += ["--backend", backend]
    assert cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["channel"] == expected
















def _opencli(installed=True, broken=False, ready=True, hint=""):
    return Mock(installed=installed, broken=broken, ready=ready, hint=hint)

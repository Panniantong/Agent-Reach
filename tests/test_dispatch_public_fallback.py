"""Regression tests for #868: added channels fall back to public-web when site backends fail transiently.

An added reddit channel whose only site backend fails with UPSTREAM_BROKEN
(HTML instead of JSON from opencli) never falls back to public-web, even
though the public-web path returns results. Expected after fix: ok=True,
backend='public-web', with the opencli failure still recorded in attempts.
"""

from unittest.mock import Mock

import pytest

from agent_reach.channels.reddit import RedditChannel
from agent_reach.channels.web import WebChannel
from agent_reach.runtime import state
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import ReachError, make_item


def _added_reddit():
    data = state.load()
    data["channels"]["reddit"] = {"added_at": state.now()}
    state.save(data)


def test_868_added_reddit_search_falls_back_to_public_web_after_opencli_html_failure(monkeypatch):
    _added_reddit()

    def opencli_search(self, **kwargs):
        raise ReachError("UPSTREAM_BROKEN",
                         "SyntaxError: Unexpected token '<', \"<body clas\"... is not valid JSON")

    monkeypatch.setattr(RedditChannel, "_opencli_search", opencli_search)
    monkeypatch.setattr(WebChannel, "_exa_search", Mock(return_value=[
        make_item(title="Python thread", url="https://www.reddit.com/r/python/comments/abc/test_post",
                  text="A public reddit thread about python testing and mocks."),
    ]))
    out = run_action(RedditChannel(), "search", {"query": "something", "limit": 2})
    assert out["ok"], out
    assert out["backend"] == "public-web"
    backends = [a["backend"] for a in out["meta"]["attempts"]]
    assert "opencli" in backends, backends
    assert any(b.startswith("public-web") for b in backends), backends


def test_868_explicit_site_backend_still_never_falls_back(monkeypatch):
    _added_reddit()

    def opencli_search(self, **kwargs):
        raise ReachError("UPSTREAM_BROKEN", "HTML instead of JSON")

    monkeypatch.setattr(RedditChannel, "_opencli_search", opencli_search)
    search = Mock(return_value=[make_item(title="x", url="https://www.reddit.com/r/python/comments/abc/t")])
    monkeypatch.setattr(WebChannel, "_exa_search", search)
    out = run_action(RedditChannel(), "search", {"query": "something", "limit": 2},
                     only_backend="opencli")
    assert not out["ok"]
    assert out["error"]["code"] == "UPSTREAM_BROKEN"
    search.assert_not_called()


def test_868_timeout_also_falls_back(monkeypatch):
    _added_reddit()

    def opencli_search(self, **kwargs):
        raise ReachError("TIMEOUT", "opencli timed out")

    monkeypatch.setattr(RedditChannel, "_opencli_search", opencli_search)
    monkeypatch.setattr(WebChannel, "_exa_search", Mock(return_value=[
        make_item(title="Python thread", url="https://www.reddit.com/r/python/comments/abc/test_post",
                  text="A public reddit thread about python testing and mocks."),
    ]))
    out = run_action(RedditChannel(), "search", {"query": "something", "limit": 2})
    assert out["ok"] and out["backend"] == "public-web"


def test_868_read_action_falls_back_to_public_read(monkeypatch):
    _added_reddit()

    def opencli_read(self, **kwargs):
        raise ReachError("UPSTREAM_BROKEN", "HTML instead of JSON")

    monkeypatch.setattr(RedditChannel, "_opencli_read", opencli_read)
    monkeypatch.setattr(WebChannel, "_jina_read", lambda self, **k: [make_item(
        title="A reddit post", url="https://www.reddit.com/r/python/comments/abc/test_post",
        text="A sufficiently long public post body " * 5)])
    out = run_action(RedditChannel(), "read",
                     {"target": "https://www.reddit.com/r/python/comments/abc/test_post"})
    assert out["ok"] and out["backend"] == "public-web"


@pytest.mark.parametrize("code", ["NEED_LOGIN", "RATE_LIMITED", "NOT_FOUND", "PLATFORM_BLOCKED"])
def test_868_final_codes_never_fall_back(monkeypatch, code):
    _added_reddit()

    def opencli_search(self, **kwargs):
        raise ReachError(code, "final failure")

    monkeypatch.setattr(RedditChannel, "_opencli_search", opencli_search)
    search = Mock(return_value=[make_item(title="x", url="https://www.reddit.com/r/python/comments/abc/t")])
    monkeypatch.setattr(WebChannel, "_exa_search", search)
    out = run_action(RedditChannel(), "search", {"query": "something", "limit": 2})
    assert not out["ok"] and out["error"]["code"] == code
    search.assert_not_called()


def test_868_public_fallback_with_no_usable_content_keeps_site_error(monkeypatch):
    _added_reddit()

    def opencli_search(self, **kwargs):
        raise ReachError("UPSTREAM_BROKEN", "HTML instead of JSON")

    monkeypatch.setattr(RedditChannel, "_opencli_search", opencli_search)
    monkeypatch.setattr(WebChannel, "_exa_search", Mock(return_value=[]))
    out = run_action(RedditChannel(), "search", {"query": "something", "limit": 2})
    assert not out["ok"] and out["error"]["code"] == "UPSTREAM_BROKEN"
    backends = [a["backend"] for a in out["meta"]["attempts"]]
    assert "opencli" in backends and any(b.startswith("public-web") for b in backends)


def test_868_multi_backend_channel_falls_back_only_after_all_fail(monkeypatch):
    """Competitor angle: two site backends, first NEED_SETUP then
    UPSTREAM_BROKEN, must still reach public-web (not stop at the first
    failure, and not fall back on the NEED_SETUP alone)."""
    from agent_reach.channels.base import Action, Channel, Param

    class TwoBackend(Channel):
        name = "reddit"
        level = "optional"
        actions = (
            Action("search", "test", (Param("query", "q"), Param("limit", "n", required=False, type=int, default=5)),
                   (("first", "_first"), ("second", "_second")),
                   public_web=("reddit.com/r/",)),
        )

        def can_handle(self, url):
            return False

        def _first(self, **kwargs):
            raise ReachError("NEED_SETUP", "first tool missing")

        def _second(self, **kwargs):
            raise ReachError("UPSTREAM_BROKEN", "HTML instead of JSON")

    _added_reddit()
    monkeypatch.setattr(WebChannel, "_exa_search", Mock(return_value=[
        make_item(title="Python thread", url="https://www.reddit.com/r/python/comments/abc/test_post",
                  text="A public reddit thread about python testing and mocks."),
    ]))
    out = run_action(TwoBackend(), "search", {"query": "something", "limit": 2})
    assert out["ok"] and out["backend"] == "public-web"
    assert [a["backend"] for a in out["meta"]["attempts"]][:2] == ["first", "second"]


def test_868_final_error_still_never_falls_back(monkeypatch):
    _added_reddit()

    def opencli_search(self, **kwargs):
        raise ReachError("BAD_INPUT", "bad query shape")

    monkeypatch.setattr(RedditChannel, "_opencli_search", opencli_search)
    search = Mock(return_value=[make_item(title="x", url="https://www.reddit.com/r/python/comments/abc/t")])
    monkeypatch.setattr(WebChannel, "_exa_search", search)
    out = run_action(RedditChannel(), "search", {"query": "something", "limit": 2})
    assert not out["ok"]
    assert out["error"]["code"] == "BAD_INPUT"
    search.assert_not_called()


def test_868_paused_site_backend_still_falls_back(monkeypatch):
    """A second search inside the opencli pause window must not lose the public route."""
    _added_reddit()
    calls = []

    def opencli_search(self, **kwargs):
        calls.append(1)
        raise ReachError("UPSTREAM_BROKEN", "HTML instead of JSON")

    monkeypatch.setattr(RedditChannel, "_opencli_search", opencli_search)
    monkeypatch.setattr(WebChannel, "_exa_search", Mock(return_value=[
        make_item(title="Python thread", url="https://www.reddit.com/r/python/comments/abc/test_post",
                  text="A public reddit thread about python testing and mocks."),
    ]))
    run_action(RedditChannel(), "search", {"query": "something", "limit": 2})
    out = run_action(RedditChannel(), "search", {"query": "something", "limit": 2})
    assert len(calls) == 1
    assert out["ok"] and out["backend"] == "public-web"
    assert out["meta"]["attempts"][0]["skipped"] is True

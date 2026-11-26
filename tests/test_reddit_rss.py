# -*- coding: utf-8 -*-
"""Reddit's public Atom feeds as the fallback when Reddit serves the browser path HTML (#906)."""

import io
import urllib.error
from email.message import Message
from unittest.mock import Mock

import pytest

from agent_reach.backends import reddit_rss
from agent_reach.channels.reddit import RedditChannel
from agent_reach.channels.web import WebChannel
from agent_reach.runtime import manage, state
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import ReachError, make_item

FEED = b"""<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom">
<title>newest submissions : Python</title>
<entry><author><name>/u/someone</name></author><category term="Python" label="r/Python"/>
<content type="html">&lt;!-- SC_OFF --&gt;&lt;div class=&quot;md&quot;&gt;&lt;p&gt;First &amp;amp; only line.&lt;/p&gt;
&lt;p&gt;Second line.&lt;/p&gt;&lt;/div&gt;&lt;!-- SC_ON --&gt; &amp;#32; submitted by &amp;#32;
&lt;a href=&quot;https://www.reddit.com/user/someone&quot;&gt; /u/someone &lt;/a&gt; &lt;br/&gt;
&lt;span&gt;&lt;a href=&quot;https://www.reddit.com/r/Python/comments/abc/t/&quot;&gt;[link]&lt;/a&gt;&lt;/span&gt; &amp;#32;
&lt;span&gt;&lt;a href=&quot;https://www.reddit.com/r/Python/comments/abc/t/&quot;&gt;[comments]&lt;/a&gt;&lt;/span&gt;</content>
<id>t3_abc</id><link href="https://www.reddit.com/r/Python/comments/abc/a_post/" />
<published>2026-11-11T08:20:43+00:00</published><title>A &amp;amp; B post</title></entry>
<entry><author><name>/u/other</name></author><id>t3_def</id>
<link href="https://www.reddit.com/r/Python/comments/def/b/" /><updated>2026-11-10T01:00:00+01:00</updated>
<title>Second</title></entry>
</feed>"""


def _http_error(code, headers=None, body=b""):
    msg = Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return urllib.error.HTTPError("https://www.reddit.com/r/python/new/.rss", code, "x", msg, io.BytesIO(body))


def test_parse_feed_normalizes_entries():
    first, second = reddit_rss.parse_feed(FEED)
    assert first["title"] == "A & B post"
    assert first["url"] == "https://www.reddit.com/r/Python/comments/abc/a_post/"
    assert first["author"] == "someone"
    assert first["published_at"] == "2026-11-11T08:20:43Z"
    assert first["text"] == "First & only line.\n\nSecond line."
    assert first["raw"] == {"id": "t3_abc", "subreddit": "r/Python", "source": "reddit-rss"}
    assert second["published_at"] == "2026-11-10T00:00:00Z"
    assert second["text"] is None


def test_parse_feed_refuses_dtds():
    with pytest.raises(ReachError) as exc:
        reddit_rss.parse_feed(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><feed/>')
    assert exc.value.code == "UPSTREAM_BROKEN"


def test_html_instead_of_feed_is_upstream_broken(monkeypatch):
    response = Mock()
    response.read.return_value = b"<body class=theme-beta>blocked</body>"
    response.headers = {"Content-Type": "text/html"}
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(reddit_rss.urllib.request, "urlopen", Mock(return_value=response))
    with pytest.raises(ReachError) as exc:
        reddit_rss.fetch("/r/python/new/.rss", 10)
    assert exc.value.code == "UPSTREAM_BROKEN"


def test_short_rate_limit_is_waited_out_once(monkeypatch):
    opened = Mock(side_effect=[_http_error(429, {"x-ratelimit-reset": "4"}), FEED])
    sleep = Mock()
    monkeypatch.setattr(reddit_rss, "_open", opened)
    monkeypatch.setattr(reddit_rss.time, "sleep", sleep)
    assert reddit_rss.fetch("/r/python/new/.rss", 30) == FEED
    sleep.assert_called_once_with(5)


@pytest.mark.parametrize("budget,reset", [(30, "300"), (6, "4")])
def test_rate_limit_never_becomes_a_channel_wide_cooldown(monkeypatch, budget, reset):
    """RATE_LIMITED pauses every Reddit action for an hour; a feed limit must not."""
    monkeypatch.setattr(reddit_rss, "_open", Mock(side_effect=_http_error(429, {"x-ratelimit-reset": reset})))
    monkeypatch.setattr(reddit_rss.time, "sleep", Mock())
    with pytest.raises(ReachError) as exc:
        reddit_rss.fetch("/r/python/new/.rss", budget)
    assert exc.value.code == "UPSTREAM_BROKEN"


def test_network_block_page_is_named(monkeypatch):
    body = b"<body>You've been blocked by network security.</body>"
    monkeypatch.setattr(reddit_rss, "_open", Mock(side_effect=_http_error(403, body=body)))
    with pytest.raises(ReachError) as exc:
        reddit_rss.fetch("/r/python/new/.rss", 10)
    assert "network" in exc.value.message


@pytest.mark.parametrize("name", ["../x", "a", "py thon", "r/" + "x" * 30, "python?limit=1"])
def test_subreddit_name_is_validated_before_any_request(monkeypatch, name):
    opened = Mock()
    monkeypatch.setattr(reddit_rss, "_open", opened)
    with pytest.raises(ReachError) as exc:
        reddit_rss.subreddit(name, 2, 10)
    assert exc.value.code == "BAD_INPUT"
    opened.assert_not_called()


def test_subreddit_requests_newest_feed_and_caps_limit(monkeypatch):
    fetch = Mock(return_value=FEED)
    monkeypatch.setattr(reddit_rss, "fetch", fetch)
    items = reddit_rss.subreddit("r/Python", 1, 10)
    assert len(items) == 1
    fetch.assert_called_once_with("/r/Python/new/.rss?limit=1", 10)


def _added_reddit():
    data = state.load()
    data["channels"]["reddit"] = {"added_at": state.now()}
    state.save(data)


def _html_from_opencli(self, **kwargs):
    raise ReachError("UPSTREAM_BROKEN", "SyntaxError: Unexpected token '<', \"<body clas\"... is not valid JSON")


def test_906_subreddit_falls_back_to_rss_when_opencli_gets_html(monkeypatch):
    _added_reddit()
    monkeypatch.setattr(RedditChannel, "_opencli_subreddit", _html_from_opencli)
    monkeypatch.setattr(reddit_rss, "fetch", Mock(return_value=FEED))
    out = run_action(RedditChannel(), "subreddit", {"name": "python", "limit": 2})
    assert out["ok"], out
    assert out["backend"] == "rss"
    assert [a["backend"] for a in out["meta"]["attempts"]] == ["opencli", "rss"]


def test_906_check_tests_the_public_route_agents_actually_get(monkeypatch):
    _added_reddit()
    monkeypatch.setattr(manage, "_channels", lambda: [RedditChannel()])
    monkeypatch.setattr(RedditChannel, "_opencli_search", _html_from_opencli)
    monkeypatch.setattr(RedditChannel, "_opencli_subreddit", _html_from_opencli)
    monkeypatch.setattr(reddit_rss, "fetch", Mock(return_value=FEED))
    monkeypatch.setattr(WebChannel, "_exa_search", Mock(return_value=[
        make_item(title="Python thread", url="https://www.reddit.com/r/python/comments/abc/test_post",
                  text="A public reddit thread about python testing and mocks."),
    ]))
    result = manage.run_checks(["reddit"])
    assert result["ok"], result
    rows = [(r["action"], r["backend"], r["passed"]) for r in result["results"]]
    assert ("search", "opencli", False) in rows
    assert ("search", "public-web", True) in rows
    assert ("subreddit", "rss", True) in rows
    assert state.load()["checks"]["reddit"]["actions"] == {"search": True, "subreddit": True}


def test_906_check_skips_the_public_route_when_the_site_backend_works(monkeypatch):
    _added_reddit()
    monkeypatch.setattr(manage, "_channels", lambda: [RedditChannel()])
    monkeypatch.setattr(RedditChannel, "_opencli_search", lambda self, **k: [make_item(title="t", url="u")])
    monkeypatch.setattr(RedditChannel, "_opencli_subreddit", lambda self, **k: [make_item(title="t", url="u")])
    exa = Mock()
    monkeypatch.setattr(WebChannel, "_exa_search", exa)
    rss = Mock(return_value=FEED)
    monkeypatch.setattr(reddit_rss, "fetch", rss)
    result = manage.run_checks(["reddit"])
    assert result["ok"], result
    exa.assert_not_called()
    assert {r["backend"] for r in result["results"] if r["action"] == "search"} == {"opencli"}

"""Quora and Fishbowl are public-first channels: public web answers, no site tool or login."""

from unittest.mock import Mock

import pytest

from agent_reach.channels.fishbowl import FishbowlChannel
from agent_reach.channels.quora import QuoraChannel
from agent_reach.channels.web import WebChannel
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import NOT_FOUND, ReachError, make_item


@pytest.mark.parametrize(("channel", "url", "other"), [
    (QuoraChannel(), "https://www.quora.com/What-is-Python", "https://www.fishbowlapp.com/"),
    (FishbowlChannel(), "https://www.fishbowlapp.com/", "https://www.quora.com/"),
])
def test_can_handle_only_its_own_host(channel, url, other):
    assert channel.can_handle(url)
    assert not channel.can_handle(other)


@pytest.mark.parametrize("channel", [QuoraChannel(), FishbowlChannel()])
def test_public_search_is_scoped_to_the_site(monkeypatch, channel):
    host = channel.actions[0].public_web[0].split("/")[0]
    search = Mock(return_value=[make_item(title="Post", url=f"https://www.{host}/post-1", text="excerpt")])
    monkeypatch.setattr(WebChannel, "_exa_search", search)
    out = run_action(channel, "search", {"query": "salary", "limit": 2})
    assert out["ok"] and out["backend"] == "public-web"
    assert f"site:{channel.actions[0].public_web[0]}" in search.call_args.kwargs["query"]


@pytest.mark.parametrize("channel", [QuoraChannel(), FishbowlChannel()])
def test_no_public_result_reports_not_found_without_a_site_tool(monkeypatch, channel):
    monkeypatch.setattr(WebChannel, "_exa_search", Mock(return_value=[]))
    out = run_action(channel, "search", {"query": "nothing", "limit": 2})
    assert not out["ok"]
    assert out["error"]["code"] == NOT_FOUND


def test_no_site_tool_hook_raises_not_found():
    with pytest.raises(ReachError) as exc:
        QuoraChannel()._no_site_tool(query="x")
    assert exc.value.code == NOT_FOUND

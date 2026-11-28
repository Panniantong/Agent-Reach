# -*- coding: utf-8 -*-
"""Dedicated tests for the ``douyin`` channel."""

import pytest

from agent_reach.channels import get_channel
from agent_reach.channels.douyin import DouyinChannel
from agent_reach.runtime.result import ReachError

ROWS = [
    {
        "rank": 1,
        "desc": "#小说推荐 一个很长很长的标题 " + "x" * 80,
        "author": "作者甲",
        "url": "https://www.douyin.com/video/1",
        "likes": 199,
    },
    {
        "rank": 2,
        "desc": "第二个视频",
        "author": "作者乙",
        "url": "https://www.douyin.com/video/2",
        "likes": 9,
    },
]


@pytest.fixture
def channel(monkeypatch):
    """A channel whose browser and site tool are stubbed out."""
    from agent_reach.channels import douyin

    calls = []
    monkeypatch.setattr(douyin, "_open_window", lambda: calls.append("window"))
    ch = DouyinChannel()
    ch.calls = calls
    return ch


def _patch_rows(channel, monkeypatch, rows):
    from agent_reach.channels import douyin

    def fake(site, args, *, timeout, login_hint=""):
        channel.calls.append((site, list(args), timeout))
        return rows

    monkeypatch.setattr(douyin, "opencli_call", fake)


def test_search_maps_rows_and_fills_missing_title(channel, monkeypatch):
    _patch_rows(channel, monkeypatch, ROWS)
    items = channel._opencli_search(query="小说推荐", limit=10, days=0, timeout=60)
    assert channel.calls[0] == "window", "a visible window must be ensured before searching"
    assert channel.calls[1][0] == "douyin"
    assert channel.calls[1][1] == ["search", "小说推荐", "--limit", "10"]
    assert [item["author"] for item in items] == ["作者甲", "作者乙"]
    assert items[0]["url"] == "https://www.douyin.com/video/1"
    assert items[0]["title"].endswith("…"), "long captions are shortened"
    assert items[1]["title"] == "第二个视频"
    assert items[0]["text"].startswith("#小说推荐")
    assert items[0]["raw"]["likes"] == 199


def test_search_passes_publish_window_only_when_requested(channel, monkeypatch):
    _patch_rows(channel, monkeypatch, ROWS)
    channel._opencli_search(query="小说", limit=5, days=7, timeout=60)
    assert channel.calls[1][1] == ["search", "小说", "--limit", "5", "--publish-time", "7"]


def test_search_trims_to_limit(channel, monkeypatch):
    _patch_rows(channel, monkeypatch, ROWS * 3)
    items = channel._opencli_search(query="小说", limit=2, days=0, timeout=60)
    assert len(items) == 2


def test_empty_site_tool_result_is_upstream_broken(channel, monkeypatch):
    _patch_rows(channel, monkeypatch, [])
    with pytest.raises(ReachError) as exc:
        channel._opencli_search(query="小说", limit=5, days=0, timeout=60)
    assert exc.value.code == "UPSTREAM_BROKEN"


def test_unknown_publish_flag_becomes_bad_input_with_a_hint(channel, monkeypatch):
    from agent_reach.channels import douyin

    def fake(site, args, *, timeout, login_hint=""):
        raise ReachError("UPSTREAM_BROKEN", "error: unknown option '--publish-time'")

    monkeypatch.setattr(douyin, "opencli_call", fake)
    with pytest.raises(ReachError) as exc:
        channel._opencli_search(query="小说", limit=5, days=7, timeout=60)
    assert exc.value.code == "BAD_INPUT"
    assert "--days" in (exc.value.hint or "")


def test_other_upstream_errors_are_passed_through(channel, monkeypatch):
    from agent_reach.channels import douyin

    def fake(site, args, *, timeout, login_hint=""):
        raise ReachError("NEED_LOGIN", "not logged in")

    monkeypatch.setattr(douyin, "opencli_call", fake)
    with pytest.raises(ReachError) as exc:
        channel._opencli_search(query="小说", limit=5, days=0, timeout=60)
    assert exc.value.code == "NEED_LOGIN"


@pytest.mark.parametrize("days", [2, 30, -1, 366])
def test_days_outside_douyin_windows_is_rejected(channel, days):
    with pytest.raises(ReachError) as exc:
        channel.validate_params("search", {"query": "小说", "limit": 5, "days": days})
    assert exc.value.code == "BAD_INPUT"


@pytest.mark.parametrize("limit", [0, 31, 100])
def test_limit_outside_the_site_tool_range_is_rejected(channel, limit):
    with pytest.raises(ReachError) as exc:
        channel.validate_params("search", {"query": "小说", "limit": limit, "days": 0})
    assert exc.value.code == "BAD_INPUT"


def test_can_handle_matches_douyin_hosts():
    ch = DouyinChannel()
    for url in [
        "https://www.douyin.com/video/7123456789012345678",
        "https://v.douyin.com/abcdefg/",
        "https://www.iesdouyin.com/share/video/7123456789012345678/",
    ]:
        assert ch.can_handle(url) is True, url
    for url in [
        "https://example.com",
        "https://douyin.com.evil.test/video/1",
        "",
        "https://user@douyin.com/video/1",
    ]:
        assert ch.can_handle(url) is False, url


def test_channel_is_registered():
    ch = get_channel("douyin")
    assert ch is not None
    assert ch.level == "optional"
    assert [a.name for a in ch.actions] == ["search"]
    assert ch.login_url.startswith("https://www.douyin.com")

# -*- coding: utf-8 -*-
"""Kuaishou channel input, response mapping and browser-route contracts."""

import json

import pytest

from agent_reach.channels.kuaishou import (
    KuaishouChannel,
    _capture_script,
    _page_url,
    _response,
    _target_id,
    _visit_page,
    _wait_for_page_target,
)
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import BAD_INPUT, PLATFORM_BLOCKED, ReachError


def test_can_handle_only_kuaishou_http_urls():
    channel = KuaishouChannel()
    assert channel.can_handle("https://www.kuaishou.com/short-video/abc123")
    assert channel.can_handle("https://kuaishou.com/profile/user_123")
    assert not channel.can_handle("https://kuaishou.com.example.org/short-video/abc123")
    assert not channel.can_handle("file:///tmp/kuaishou")


def test_target_id_accepts_only_matching_official_routes():
    assert _target_id("https://www.kuaishou.com/short-video/work_1", "work") == "work_1"
    assert _target_id("user-1", "user") == "user-1"
    with pytest.raises(ReachError) as error:
        _target_id("https://example.org/short-video/work_1", "work")
    assert error.value.code == BAD_INPUT
    with pytest.raises(ReachError) as error:
        _target_id("https://www.kuaishou.com/profile/user_1", "work")
    assert error.value.code == BAD_INPUT


def test_page_urls_encode_search_terms_and_rebuild_targets_on_official_origin():
    assert _page_url("search", "茶 & 咖啡") == (
        "https://www.kuaishou.com/search/video?searchKey=%E8%8C%B6%20%26%20%E5%92%96%E5%95%A1"
    )
    assert _page_url("read", "https://www.kuaishou.com/short-video/work-1") == (
        "https://www.kuaishou.com/short-video/work-1"
    )
    assert _page_url("user_works", "https://www.kuaishou.com/profile/user_1") == (
        "https://www.kuaishou.com/profile/user_1"
    )


def test_capture_script_limits_observation_to_expected_first_party_paths():
    script = _capture_script(("/rest/v/search/feed",))
    assert '"/rest/v/search/feed"' in script
    assert "https://www.kuaishou.com" in script
    assert "rows.length >= 12" in script


def test_wait_for_page_target_handles_chrome_target_registration_race(monkeypatch):
    from agent_reach.runtime import cdp

    answers = [[], [{"id": "target-1", "type": "page"}]]
    monkeypatch.setattr(cdp, "_json", lambda path: answers.pop(0))
    monkeypatch.setattr("agent_reach.channels.kuaishou.time.sleep", lambda _delay: None)
    assert _wait_for_page_target("target-1", timeout=0.1) is True


def test_visit_page_keeps_injection_navigation_and_read_in_one_cdp_session(monkeypatch):
    from agent_reach.runtime import browser, cdp, session_reuse

    feed = {"result": 1, "feeds": [{"photo": {"id": "work-1"}}]}
    commands = []
    class FakeTargetSession:
        def __init__(self, target_id):
            assert target_id == "target-1"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def call(self, method, params=None):
            commands.append((method, params))
            if method == "Runtime.evaluate":
                return {"result": {"value": json.dumps([
                    {"path": "/rest/v/search/feed", "status": 200, "body": json.dumps(feed)}
                ])}}
            return {}

    monkeypatch.setattr(session_reuse, "prepare", lambda _channel: {})
    monkeypatch.setattr(browser, "ensure_running", lambda: None)
    monkeypatch.setattr(browser, "save_session", lambda: None)
    monkeypatch.setattr(cdp, "call", lambda method, *_args, **_kwargs: (
        {"targetId": "target-1"} if method == "Target.createTarget" else {"success": True}
    ))
    monkeypatch.setattr(cdp, "TargetSession", FakeTargetSession)
    monkeypatch.setattr(
        "agent_reach.channels.kuaishou._wait_for_page_target", lambda _target_id: True
    )

    rows = _visit_page("https://www.kuaishou.com/new-reco", ("/rest/v/search/feed",), 10)

    methods = [method for method, _params in commands]
    assert methods.index("Page.addScriptToEvaluateOnNewDocument") < methods.index("Page.navigate")
    assert methods[-1] == "Runtime.evaluate"
    assert rows[0]["path"] == "/rest/v/search/feed"


def test_response_requires_exact_graphql_operation_and_maps_platform_block():
    rows = [
        {"path": "/graphql", "status": 200, "requestBody": '{"operationName":"other"}', "body": "{}"},
        {"path": "/graphql", "status": 403, "requestBody": '{"operationName":"visionVideoDetail"}', "body": "{}"},
    ]
    with pytest.raises(ReachError) as error:
        _response(rows, "/graphql", "visionVideoDetail")
    assert error.value.code == PLATFORM_BLOCKED


def test_search_action_maps_first_party_feed_rows(monkeypatch):
    captured = {}

    def visit(url, paths, timeout):
        captured.update(url=url, paths=paths, timeout=timeout)
        return [{
            "path": "/rest/v/search/feed",
            "status": 200,
            "body": json.dumps({"result": 1, "feeds": [{
                "photo": {"id": "work-1", "caption": "A quiet walk", "timestamp": 1780000000000},
                "author": {"name": "Creator"},
            }]}),
        }]

    monkeypatch.setattr("agent_reach.channels.kuaishou._visit_page", visit)
    result = run_action(KuaishouChannel(), "search", {"query": "散步", "limit": 1})

    assert result["ok"] is True
    assert result["items"][0]["title"] == "A quiet walk"
    assert result["items"][0]["author"] == "Creator"
    assert result["items"][0]["url"].endswith("/short-video/work-1")
    assert captured["paths"] == ("/rest/v/search/feed",)
    assert "searchKey=%E6%95%A3%E6%AD%A5" in captured["url"]


def test_search_rejects_invalid_limit_without_opening_browser(monkeypatch):
    monkeypatch.setattr(
        "agent_reach.channels.kuaishou._visit_page",
        lambda *args, **kwargs: pytest.fail("invalid input must not start a browser"),
    )
    result = run_action(KuaishouChannel(), "search", {"query": "tea", "limit": 21})
    assert result["ok"] is False
    assert result["error"]["code"] == BAD_INPUT


def test_read_requires_requested_graphql_photo_id(monkeypatch):
    payload = {"data": {"visionVideoDetail": {
        "status": 1,
        "photo": {"id": "work-2", "caption": "Verified detail"},
        "author": {"name": "Creator"},
    }}}
    monkeypatch.setattr(
        "agent_reach.channels.kuaishou._visit_page",
        lambda *args, **kwargs: [{
            "path": "/graphql",
            "status": 200,
            "requestBody": '{"operationName":"visionVideoDetail"}',
            "body": json.dumps(payload),
        }],
    )
    result = run_action(KuaishouChannel(), "read", {"target": "work-2"})
    assert result["ok"] is True
    assert result["items"][0]["title"] == "Verified detail"
    assert result["items"][0]["author"] == "Creator"

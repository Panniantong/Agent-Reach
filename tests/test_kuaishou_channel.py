# -*- coding: utf-8 -*-
"""Kuaishou channel input, response mapping and browser-route contracts."""

import json
import shutil
import subprocess

import pytest

from agent_reach.channels.kuaishou import (
    KuaishouChannel,
    _capture_script,
    _page_detail_script,
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


@pytest.mark.parametrize("source", ["page-state", "network"])
def test_visit_detail_waits_for_detail_after_unrelated_graphql(monkeypatch, source):
    from agent_reach.runtime import browser, cdp, session_reuse

    detail = {"status": 1, "photo": {"id": "work-1", "caption": "Requested work"}}
    unrelated = {"path": "/graphql", "requestBody": '{"operationName":"checkLoginQuery"}'}
    response = {"path": "/graphql", "status": 200,
                "requestBody": '{"operationName":"visionVideoDetail"}',
                "body": json.dumps({"data": {"visionVideoDetail": detail}})}
    polls = []

    class FakeTargetSession:
        def __init__(self, target_id):
            assert target_id == "target-1"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def call(self, method, params=None):
            if method != "Runtime.evaluate":
                return {}
            if "__APOLLO_STATE__" in params["expression"]:
                value = detail if source == "page-state" and polls else None
                return {"result": {"value": value}}
            polls.append(True)
            rows = [unrelated] if len(polls) == 1 else [unrelated, response]
            return {"result": {"value": json.dumps(rows)}}

    monkeypatch.setattr(session_reuse, "prepare", lambda _channel: {})
    monkeypatch.setattr(browser, "ensure_running", lambda: None)
    monkeypatch.setattr(browser, "save_session", lambda: None)
    monkeypatch.setattr(cdp, "call", lambda method, *_args, **_kwargs: (
        {"targetId": "target-1"} if method == "Target.createTarget" else {}
    ))
    monkeypatch.setattr(cdp, "TargetSession", FakeTargetSession)
    monkeypatch.setattr("agent_reach.channels.kuaishou._wait_for_page_target", lambda _id: True)
    monkeypatch.setattr("agent_reach.channels.kuaishou.time.sleep", lambda _delay: None)

    rows = _visit_page("https://www.kuaishou.com/short-video/work-1", ("/graphql",), 2,
                       detail_id="work-1")

    assert polls
    if source == "page-state":
        assert rows == [{"source": "page-state", "detail": detail}]
    else:
        assert len(polls) == 2
        assert rows == [response]


@pytest.mark.parametrize("photo_id,success", [("work-1", True), ("other", False)])
def test_read_validates_target_even_for_server_rendered_detail(monkeypatch, photo_id, success):
    detail = {"status": 1, "photo": {"id": photo_id, "caption": "Requested work"},
              "author": {"name": "Creator"}}
    monkeypatch.setattr("agent_reach.channels.kuaishou._visit_page", lambda *a, **kw: [
        {"source": "page-state", "detail": detail}
    ])

    result = run_action(KuaishouChannel(), "read", {"target": "work-1"})

    assert result["ok"] is success
    if success:
        assert result["items"][0]["title"] == "Requested work"
    else:
        assert result["items"] == []
        assert result["error"]["code"] == "UPSTREAM_BROKEN"


def test_page_detail_script_resolves_only_requested_apollo_detail():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is optional for unit tests; required by browser channels")
    query = 'visionVideoDetail({"page":"detail","photoId":"work-1"})'
    cache = {
        "ROOT_QUERY": {
            'visionVideoDetail({"page":"detail","photoId":"other"})':
                {"type": "id", "id": "detail-other"},
            query: {"type": "id", "id": "detail-1"},
        },
        "detail-other": {"status": 1, "photo": {"id": "other"}},
        "detail-1": {"status": 1, "photo": {"type": "id", "id": "Photo:work-1"},
                     "author": {"type": "id", "id": "User:user-1"}},
        "Photo:work-1": {"id": "work-1", "caption": "Requested work"},
        "User:user-1": {"id": "user-1", "name": "Creator"},
    }
    setup = "globalThis.window = " + json.dumps({"__APOLLO_STATE__": {"defaultClient": cache}})
    script = setup + ";console.log(JSON.stringify(" + _page_detail_script("work-1") + "));"

    result = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True,
                            timeout=5)
    detail = json.loads(result.stdout)

    assert detail["photo"] == {"id": "work-1", "caption": "Requested work"}
    assert detail["author"]["name"] == "Creator"


def test_capture_ignores_unrelated_graphql_before_filling_response_limit():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is optional for unit tests; required by browser channels")
    setup = """
globalThis.window = globalThis;
globalThis.location = {href: 'https://www.kuaishou.com/short-video/work-1'};
globalThis.XMLHttpRequest = class {open() {} send() {}};
globalThis.fetch = async () => new Response('{}', {status: 200});
"""
    exercise = """
(async () => {
  const url = 'https://www.kuaishou.com/graphql';
  for (let i = 0; i < 20; i++)
    await fetch(url, {body: JSON.stringify({operationName: 'checkLoginQuery'})});
  await fetch(url, {body: JSON.stringify({operationName: 'visionVideoDetail'})});
  await new Promise(resolve => setTimeout(resolve, 20));
  console.log(JSON.stringify(window.__agentReachKuaishouResponses));
})();
"""
    script = setup + _capture_script(("/graphql",), "visionVideoDetail") + exercise

    result = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True,
                            timeout=5)
    rows = json.loads(result.stdout)

    assert len(rows) == 1
    assert json.loads(rows[0]["requestBody"])["operationName"] == "visionVideoDetail"

# -*- coding: utf-8 -*-
"""Hosted transcript providers: off by default, explicit, HTTP mocked."""

import pytest

from agent_reach.backends import transcript_providers as tp
from agent_reach.channels.youtube import YouTubeChannel
from agent_reach.runtime.result import ReachError


class _Cfg:
    def __init__(self, **data):
        self.data = data

    def get(self, key, default=None):
        return self.data.get(key, default)


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def test_not_configured_is_need_setup_and_makes_no_request(monkeypatch):
    monkeypatch.setattr(tp.requests, "post", lambda *a, **k: pytest.fail("no HTTP call expected"))
    with pytest.raises(ReachError) as exc:
        tp.fetch(URL, ["en"], 60, config=_Cfg())
    assert exc.value.code == "NEED_SETUP"


def test_unknown_provider(monkeypatch):
    with pytest.raises(ReachError) as exc:
        tp.fetch(URL, ["en"], 60, config=_Cfg(transcript_provider="nope", transcript_key="k"))
    assert exc.value.code == "NEED_SETUP" and "shephouse-apify" in exc.value.message


def test_shephouse_success_sends_expected_request(monkeypatch):
    seen = {}

    def post(url, params, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json)
        return _Resp(200, [{"status": "OK", "text": "hello world", "language": "en"}])

    monkeypatch.setattr(tp.requests, "post", post)
    text, lang, name = tp.fetch(URL, ["de", "en"], 60,
                                config=_Cfg(transcript_provider="Shephouse-Apify", transcript_key="tok"))
    assert (text, lang, name) == ("hello world", "en", "shephouse-apify")
    assert "run-sync-get-dataset-items" in seen["url"]
    assert seen["headers"]["Authorization"] == "Bearer tok"
    assert seen["json"]["startUrls"] == [{"url": URL}] and seen["json"]["languages"] == ["de", "en"]


@pytest.mark.parametrize("item,code", [
    ({"status": "ERROR", "errorCode": "NO_CAPTIONS"}, "NOT_FOUND"),
    ({"status": "ERROR", "errorCode": "SOMETHING"}, "UPSTREAM_BROKEN"),
])
def test_shephouse_failure_rows(monkeypatch, item, code):
    monkeypatch.setattr(tp.requests, "post", lambda *a, **k: _Resp(200, [item]))
    with pytest.raises(ReachError) as exc:
        tp.shephouse_apify(URL, ["en"], "tok", 60)
    assert exc.value.code == code


@pytest.mark.parametrize("status,code", [(401, "NEED_SETUP"), (402, "NEED_SETUP"), (429, "RATE_LIMITED"), (500, "UPSTREAM_BROKEN")])
def test_shephouse_http_errors(monkeypatch, status, code):
    monkeypatch.setattr(tp.requests, "post", lambda *a, **k: _Resp(status))
    with pytest.raises(ReachError) as exc:
        tp.shephouse_apify(URL, ["en"], "tok", 60)
    assert exc.value.code == code
    assert "tok" not in exc.value.message


def test_network_error_does_not_leak_key(monkeypatch):
    def boom(*a, **k):
        raise tp.requests.ConnectionError("Bearer tok")

    monkeypatch.setattr(tp.requests, "post", boom)
    with pytest.raises(ReachError) as exc:
        tp.shephouse_apify(URL, ["en"], "tok", 60)
    assert "tok" not in exc.value.message


def test_youtube_subtitle_backend_order_keeps_ytdlp_default():
    action = next(a for a in YouTubeChannel.actions if a.name == "subtitle")
    assert [label for label, _ in action.backends] == ["yt-dlp", "hosted"]


def test_hosted_subtitle_item(monkeypatch):
    monkeypatch.setattr(tp, "fetch", lambda url, langs, timeout: ("txt", "en", "shephouse-apify"))
    items = YouTubeChannel()._hosted_subtitle(target="jNQXAC9IVRw", lang="en", timeout=60)
    assert items[0]["text"] == "txt"
    assert items[0]["raw"] == {"lang": "en", "provider": "shephouse-apify"}


def test_configure_accepts_new_keys():
    from agent_reach.runtime.manage import CONFIG_KEYS

    assert CONFIG_KEYS["transcript-provider"] == "transcript_provider"
    assert CONFIG_KEYS["transcript-key"] == "transcript_key"

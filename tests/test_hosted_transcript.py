# -*- coding: utf-8 -*-
"""Tests for the hosted transcript backend: key handling, error mapping, no key leaks.

The HTTP call is injected, so every branch runs offline.
"""

import pytest
import requests

from agent_reach import hosted_transcript
from agent_reach.channels.youtube import YouTubeChannel
from agent_reach.config import Config
from agent_reach.runtime.result import ReachError

URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
KEY = "gyt_secret_key_value"


class _Response:
    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self.ok = status < 400
        self._body = body
        self._text = text

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


def _config(tmp_path, **values):
    cfg = Config(tmp_path / "config.yaml")
    for key, value in values.items():
        cfg.set(key, value)
    return cfg


def _fetch(tmp_path, response=None, error=None, **values):
    """Run fetch with a stub HTTP layer; returns (result, request seen by the stub)."""
    seen = {}

    def http_get(endpoint, **kwargs):
        seen.update(endpoint=endpoint, **kwargs)
        if error:
            raise error
        return response

    cfg = _config(tmp_path, **({"transcript_api_key": KEY} | values))
    result = hosted_transcript.fetch(URL, "en", timeout=12, config=cfg, http_get=http_get)
    return result, seen


def _code(tmp_path, response=None, error=None, **values):
    with pytest.raises(ReachError) as exc:
        _fetch(tmp_path, response, error, **values)
    assert KEY not in exc.value.message
    assert KEY not in (exc.value.hint or "")
    return exc.value.code


def test_success_returns_title_and_text_and_keeps_key_in_the_header_only(tmp_path):
    body = {"success": True, "data": {"title": "Me at the zoo", "transcript": "All right, so here we are"}}
    (title, text), seen = _fetch(tmp_path, _Response(200, body))
    assert (title, text) == ("Me at the zoo", "All right, so here we are")
    assert seen["endpoint"] == "https://getyoutubetranscript.com/api/v1/transcript"
    assert seen["params"] == {"v": URL, "language": "en"}
    assert seen["headers"] == {"Authorization": f"Bearer {KEY}"}
    assert KEY not in repr(seen["params"])
    assert seen["timeout"] == 12


def test_missing_key_is_need_setup_with_a_configure_hint(tmp_path):
    cfg = _config(tmp_path)
    with pytest.raises(ReachError) as exc:
        hosted_transcript.fetch(URL, "en", timeout=5, config=cfg, http_get=lambda *a, **k: pytest.fail("no key, no request"))
    assert exc.value.code == "NEED_SETUP"
    assert "configure transcript-api-key" in exc.value.hint


def _two_providers(monkeypatch):
    other = {
        "endpoint": "https://other.example/transcript",
        "query": lambda video_url, lang: {"url": video_url, "lang": lang},
        "text": lambda body: body.get("text"),
        "title": lambda body: None,
    }
    monkeypatch.setattr(hosted_transcript, "PROVIDERS", {**hosted_transcript.PROVIDERS, "other": other})


def test_with_several_providers_the_user_must_choose_one(tmp_path, monkeypatch):
    _two_providers(monkeypatch)
    cfg = _config(tmp_path, transcript_api_key=KEY)
    with pytest.raises(ReachError) as exc:
        hosted_transcript.fetch(URL, "en", timeout=5, config=cfg, http_get=lambda *a, **k: pytest.fail("no choice, no request"))
    assert exc.value.code == "NEED_SETUP"
    assert "getyoutubetranscript, other" in exc.value.hint
    assert "configure transcript-api-provider" in exc.value.hint


def test_an_explicit_provider_choice_routes_the_request_to_it(tmp_path, monkeypatch):
    _two_providers(monkeypatch)
    (title, text), seen = _fetch(tmp_path, _Response(200, {"text": "hola"}), transcript_api_provider="other")
    assert (title, text) == (None, "hola")
    assert seen["endpoint"] == "https://other.example/transcript"
    assert seen["params"] == {"url": URL, "lang": "en"}


def test_unknown_provider_is_bad_input_and_sends_nothing(tmp_path):
    cfg = _config(tmp_path, transcript_api_key=KEY, transcript_api_provider="nope")
    with pytest.raises(ReachError) as exc:
        hosted_transcript.fetch(URL, "en", timeout=5, config=cfg, http_get=lambda *a, **k: pytest.fail("no request"))
    assert exc.value.code == "BAD_INPUT"
    assert "getyoutubetranscript" in exc.value.message


@pytest.mark.parametrize(
    "status, expected",
    [(401, "NEED_SETUP"), (402, "NEED_SETUP"), (403, "NEED_SETUP"), (404, "NOT_FOUND"), (429, "RATE_LIMITED"), (500, "UPSTREAM_BROKEN")],
)
def test_http_status_maps_to_one_code(tmp_path, status, expected):
    assert _code(tmp_path, _Response(status, {"message": "provider said no"})) == expected


def test_refused_key_gets_its_own_hint_not_the_generic_install_one(tmp_path):
    with pytest.raises(ReachError) as exc:
        _fetch(tmp_path, _Response(401, {"message": "This API key is invalid or has been revoked."}))
    assert "refused the key" in exc.value.hint
    assert "doctor" not in exc.value.hint


def test_provider_message_is_passed_through_but_capped(tmp_path):
    with pytest.raises(ReachError) as exc:
        _fetch(tmp_path, _Response(402, {"message": "out of credits " + "x" * 500}))
    assert exc.value.message.startswith("getyoutubetranscript: out of credits")
    assert len(exc.value.message) < 260


def test_error_without_json_falls_back_to_the_status(tmp_path):
    with pytest.raises(ReachError) as exc:
        _fetch(tmp_path, _Response(502))
    assert exc.value.message == "getyoutubetranscript: HTTP 502"


def test_ok_reply_that_is_not_json_is_upstream_broken(tmp_path):
    assert _code(tmp_path, _Response(200)) == "UPSTREAM_BROKEN"


@pytest.mark.parametrize("body", [{"success": True, "data": {"transcript": ""}}, {"success": True}, {"data": None}, []])
def test_empty_or_oddly_shaped_body_is_not_found(tmp_path, body):
    assert _code(tmp_path, _Response(200, body)) == "NOT_FOUND"


def test_timeout_and_network_errors_never_echo_the_request(tmp_path):
    assert _code(tmp_path, error=requests.Timeout(f"slow {KEY}")) == "TIMEOUT"
    assert _code(tmp_path, error=requests.ConnectionError(f"down {KEY}")) == "UPSTREAM_BROKEN"


def test_channel_action_is_explicit_and_has_no_fallback_backend():
    action = next(a for a in YouTubeChannel.actions if a.name == "transcript")
    assert [label for label, _method in action.backends] == ["hosted"]
    subtitle = next(a for a in YouTubeChannel.actions if a.name == "subtitle")
    assert [label for label, _method in subtitle.backends] == ["yt-dlp"]


def test_channel_rejects_a_non_youtube_target_before_any_request(monkeypatch):
    monkeypatch.setattr(hosted_transcript, "fetch", lambda *a, **k: pytest.fail("must not be called"))
    with pytest.raises(ReachError) as exc:
        YouTubeChannel()._hosted_transcript(target="https://example.com/x", lang="en", timeout=5)
    assert exc.value.code == "BAD_INPUT"


def test_channel_builds_one_item_from_the_provider_reply(monkeypatch):
    monkeypatch.setattr(hosted_transcript, "fetch", lambda url, lang, *, timeout: ("Me at the zoo", "hello"))
    items = YouTubeChannel()._hosted_transcript(target="jNQXAC9IVRw", lang="es", timeout=5)
    assert len(items) == 1
    assert items[0]["text"] == "hello"
    assert items[0]["title"] == "Me at the zoo"
    assert items[0]["url"] == URL

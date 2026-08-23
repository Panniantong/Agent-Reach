import argparse
import json

import pytest
import requests

from agent_reach import exa_api


def search_args(**overrides):
    values = {
        "query": "official Python TaskGroup cancellation documentation",
        "num_results": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_search_defaults_match_web_search_exa():
    assert exa_api.build_search_payload(search_args()) == {
        "query": "official Python TaskGroup cancellation documentation",
        "type": "auto",
        "numResults": 10,
        "contents": {"highlights": True},
    }


def test_search_explicit_count_and_inline_category_match_web_search_exa():
    assert exa_api.build_search_payload(
        search_args(query="category:personal site distributed systems", num_results=5)
    ) == {
        "query": "distributed systems",
        "type": "auto",
        "numResults": 5,
        "category": "personal site",
        "contents": {"highlights": True},
    }


def test_search_removes_only_the_first_inline_category_like_web_search_exa():
    assert exa_api.build_search_payload(
        search_args(query="category:people Ada category:company", num_results=1)
    ) == {
        "query": "Ada category:company",
        "type": "auto",
        "numResults": 1,
        "category": "people",
        "contents": {"highlights": True},
    }


def test_contents_default_matches_web_fetch_exa():
    parser = exa_api.build_parser()
    args = parser.parse_args(["contents", "https://example.com/a", "https://example.com/b"])
    assert exa_api.build_contents_payload(args) == {
        "urls": ["https://example.com/a", "https://example.com/b"],
        "text": {"maxCharacters": 3000},
    }


def test_request_sends_key_only_as_header(monkeypatch):
    observed = {}

    class Response:
        ok = True
        status_code = 200

        @staticmethod
        def json():
            return {"results": []}

    def fake_post(url, *, headers, json, timeout):
        observed.update(url=url, headers=headers, json=json, timeout=timeout)
        return Response()

    monkeypatch.setattr(exa_api.requests, "post", fake_post)
    result = exa_api.request_json(
        "search",
        {"query": "test", "type": "auto", "numResults": 1},
        api_key="opaque-test-key",
        timeout=3,
    )
    assert result == {"results": []}
    assert observed["headers"]["x-api-key"] == "opaque-test-key"
    assert "opaque-test-key" not in observed["url"]
    assert "opaque-test-key" not in repr(observed["json"])


def test_search_output_matches_web_search_exa_shape():
    rendered = exa_api.format_search_response(
        {
            "results": [
                {
                    "title": "Example",
                    "url": "https://example.com",
                    "publishedDate": "2026-08-23",
                    "author": "Author",
                    "highlights": ["First", "Second"],
                }
            ]
        }
    )
    assert rendered == (
        "Title: Example\n"
        "URL: https://example.com\n"
        "Published: 2026-08-23\n"
        "Author: Author\n"
        "Highlights:\nFirst\nSecond"
    )


def test_contents_output_matches_web_fetch_exa_shape():
    rendered, is_error = exa_api.format_contents_response(
        {
            "results": [
                {
                    "title": "Example",
                    "url": "https://example.com",
                    "publishedDate": "2026-08-23T12:00:00Z",
                    "author": "Author",
                    "text": "Body",
                }
            ]
        }
    )
    assert is_error is False
    assert rendered == (
        "# Example\nURL: https://example.com\nPublished: 2026-08-23\nAuthor: Author\n\nBody"
    )


def test_request_retries_the_same_transient_statuses_as_exa_mcp(monkeypatch):
    statuses = iter([500, 503, 200])
    calls = []
    sleeps = []

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.ok = status_code == 200

        def json(self):
            return {"results": []}

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return Response(next(statuses))

    monkeypatch.setattr(exa_api.requests, "post", fake_post)
    monkeypatch.setattr(exa_api.time, "sleep", sleeps.append)
    assert exa_api.request_json("search", {"query": "test"}, api_key="key") == {"results": []}
    assert len(calls) == 3
    assert sleeps == [1, 2]


@pytest.mark.parametrize(
    ("status_code", "exit_code", "message"),
    [
        (401, 4, "API key rejected"),
        (402, 5, "credits exhausted"),
        (429, 6, "rate limit"),
    ],
)
def test_auth_and_quota_errors_are_stable_and_do_not_leak_key(
    monkeypatch, status_code, exit_code, message
):
    class Response:
        ok = False

        def __init__(self):
            self.status_code = status_code

        @staticmethod
        def json():
            return {"message": "opaque-test-key"}

    monkeypatch.setattr(exa_api.requests, "post", lambda *args, **kwargs: Response())
    with pytest.raises(exa_api.ExaClientError) as raised:
        exa_api.request_json("search", {"query": "test"}, api_key="opaque-test-key")
    assert raised.value.exit_code == exit_code
    assert message in str(raised.value)
    assert "opaque-test-key" not in str(raised.value)


def test_status_is_local_only(monkeypatch, capsys):
    monkeypatch.setattr(exa_api, "require_api_key", lambda: "opaque-test-key")
    monkeypatch.setattr(
        exa_api.requests,
        "post",
        lambda *args, **kwargs: pytest.fail("status must not call Exa"),
    )
    assert exa_api.main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "configured": True,
        "backend": "Exa REST API",
        "live_probe": False,
    }


def test_transport_failure_reports_only_exception_type(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError("opaque-test-key")

    monkeypatch.setattr(exa_api.requests, "post", fail)
    with pytest.raises(exa_api.ExaClientError) as raised:
        exa_api.request_json("search", {"query": "test"}, api_key="opaque-test-key")
    assert str(raised.value) == "transport failure: ConnectionError"

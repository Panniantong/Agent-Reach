# -*- coding: utf-8 -*-
"""Tests for the external collection result schema helpers."""

from agent_reach.results import (
    apply_item_text_mode,
    apply_raw_mode,
    build_error,
    build_item,
    build_pagination_meta,
    build_result,
)


def test_build_item_and_result_shape():
    item = build_item(
        item_id="item-1",
        kind="page",
        title="Example",
        url="https://example.com",
        text="hello",
        author="alice",
        published_at="2026-04-10T00:00:00Z",
        source="web",
        extras={"reader_url": "https://r.jina.ai/https://example.com"},
    )
    payload = build_result(
        ok=True,
        channel="web",
        operation="read",
        items=[item],
        raw={"ok": True},
        meta={"input": "https://example.com"},
        error=None,
    )

    assert set(item) == {
        "id",
        "kind",
        "title",
        "url",
        "text",
        "author",
        "published_at",
        "source",
        "canonical_url",
        "source_item_id",
        "engagement",
        "media_references",
        "identifiers",
        "extras",
    }
    assert set(payload) == {
        "schema_version",
        "agent_reach_version",
        "ok",
        "channel",
        "operation",
        "items",
        "raw",
        "meta",
        "error",
    }
    assert payload["schema_version"]
    assert payload["agent_reach_version"]
    assert payload["meta"]["schema_version"]
    assert item["canonical_url"] == "https://example.com"
    assert item["source_item_id"] == "item-1"
    assert item["identifiers"] == {"domain": "example.com"}
    assert payload["meta"]["count"] == 1


def test_build_error_shape():
    error = build_error(code="invalid_input", message="bad input", details={"field": "input"})

    assert error == {
        "code": "invalid_input",
        "category": "invalid_input",
        "message": "bad input",
        "details": {"field": "input"},
        "retryable": False,
    }


def test_build_item_normalizes_engagement_media_and_identifiers():
    item = build_item(
        item_id="repo-1",
        kind="repository",
        title="Repo",
        url="HTTPS://GitHub.com/OpenAI/Example/#readme",
        text=None,
        author="openai",
        published_at=None,
        source="github",
        extras={
            "repo_full_name": "OpenAI/Example",
            "stars": "1,234",
            "forks": 5,
            "media_references": [{"type": "image", "url": "https://example.com/a.png"}],
        },
        source_item_id="OpenAI/Example",
    )

    assert item["canonical_url"] == "https://github.com/OpenAI/Example"
    assert item["source_item_id"] == "OpenAI/Example"
    assert item["engagement"] == {"stars": 1234, "forks": 5}
    assert item["media_references"] == [{"type": "image", "url": "https://example.com/a.png"}]
    assert item["identifiers"] == {
        "domain": "github.com",
        "repo_full_name": "OpenAI/Example",
    }


def test_apply_raw_mode_can_minimize_or_truncate_raw_payload():
    payload = build_result(
        ok=True,
        channel="web",
        operation="read",
        items=[],
        raw={"body": "x" * 100},
        meta={},
        error=None,
    )

    minimized = apply_raw_mode(payload, raw_mode="minimal")
    truncated = apply_raw_mode(payload, raw_mode="full", raw_max_bytes=10)
    omitted = apply_raw_mode(payload, raw_mode="none")

    assert minimized["raw"]["raw_mode"] == "minimal"
    assert minimized["meta"]["raw_payload_minimized"] is True
    assert truncated["raw"]["raw_mode"] == "truncated"
    assert truncated["meta"]["raw_payload_truncated"] is True
    assert omitted["raw"] is None
    assert omitted["meta"]["raw_payload_omitted"] is True


def test_apply_item_text_mode_can_snippet_or_omit_item_text():
    payload = build_result(
        ok=True,
        channel="web",
        operation="read",
        items=[
            build_item(
                item_id="item-1",
                kind="page",
                title="Example",
                url="https://example.com",
                text="abcdefghijklmnopqrstuvwxyz",
                author=None,
                published_at=None,
                source="web",
            )
        ],
        raw=None,
        meta={},
        error=None,
    )

    snippet = apply_item_text_mode(payload, item_text_mode="snippet", item_text_max_chars=5)
    omitted = apply_item_text_mode(payload, item_text_mode="none")

    assert snippet["items"][0]["text"] == "abcde"
    assert snippet["meta"]["item_text_mode"] == "snippet"
    assert snippet["meta"]["item_text_max_chars"] == 5
    assert omitted["items"][0]["text"] is None
    assert omitted["meta"]["item_text_mode"] == "none"


def test_build_result_keeps_flat_and_nested_pagination_meta():
    payload = build_result(
        ok=True,
        channel="github",
        operation="search",
        items=[],
        raw=[],
        meta=build_pagination_meta(
            limit=5,
            requested_page_size=2,
            requested_max_pages=3,
            requested_page=4,
            page_size=2,
            pages_fetched=1,
            next_page=5,
            has_more=True,
            total_available=12,
        ),
        error=None,
    )

    assert payload["meta"]["requested_limit"] == 5
    assert payload["meta"]["page_size"] == 2
    assert payload["meta"]["next_page"] == 5
    assert payload["meta"]["pagination"] == {
        "requested_limit": 5,
        "requested_page_size": 2,
        "page_size": 2,
        "requested_max_pages": 3,
        "requested_page": 4,
        "pages_fetched": 1,
        "next_page": 5,
        "has_more": True,
        "total_available": 12,
    }

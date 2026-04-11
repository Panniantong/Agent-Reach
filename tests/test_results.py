# -*- coding: utf-8 -*-
"""Tests for the external collection result schema helpers."""

from agent_reach.results import build_error, build_item, build_pagination_meta, build_result


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
        "extras",
    }
    assert set(payload) == {"ok", "channel", "operation", "items", "raw", "meta", "error"}
    assert payload["meta"]["schema_version"]
    assert payload["meta"]["count"] == 1


def test_build_error_shape():
    error = build_error(code="invalid_input", message="bad input", details={"field": "input"})

    assert error == {
        "code": "invalid_input",
        "message": "bad input",
        "details": {"field": "input"},
    }


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

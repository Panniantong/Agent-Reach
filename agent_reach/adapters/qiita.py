# -*- coding: utf-8 -*-
"""Qiita collection adapter."""

from __future__ import annotations

import time
import warnings

from agent_reach.media_references import (
    build_media_reference,
    dedupe_media_references,
    extract_image_urls,
)
from agent_reach.results import (
    CollectionResult,
    NormalizedItem,
    build_item,
    build_pagination_meta,
    parse_timestamp,
)
from agent_reach.source_hints import article_source_hints

from .base import BaseAdapter

_UA = "agent-reach/1.4.0 (+https://github.com/iwachacha/Agent-Reach)"
_ITEMS_API = "https://qiita.com/api/v2/items"
_BODY_SNIPPET_CHARS = 500
_BODY_MODES = {"none", "snippet", "full"}
_PAGE_SIZE_MAX = 100


def _import_requests():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"urllib3 .* doesn't match a supported version!",
        )
        import requests

    return requests


class QiitaAdapter(BaseAdapter):
    """Search public Qiita items through Qiita API v2."""

    channel = "qiita"
    operations = ("search",)

    def search(
        self,
        query: str,
        limit: int = 10,
        body_mode: str = "full",
        page_size: int | None = None,
        max_pages: int | None = None,
        page: int | None = None,
    ) -> CollectionResult:
        started_at = time.perf_counter()
        if body_mode not in _BODY_MODES:
            return self.error_result(
                "search",
                code="invalid_input",
                message="body_mode must be one of: none, snippet, full",
                meta=self.make_meta(
                    value=query,
                    limit=limit,
                    started_at=started_at,
                    body_mode=body_mode,
                    **build_pagination_meta(
                        limit=limit,
                        requested_page_size=page_size,
                        requested_max_pages=max_pages,
                        requested_page=page,
                    ),
                ),
            )
        if page_size is not None and page_size < 1:
            return self.error_result(
                "search",
                code="invalid_input",
                message="page_size must be greater than or equal to 1",
                meta=self.make_meta(
                    value=query,
                    limit=limit,
                    started_at=started_at,
                    body_mode=body_mode,
                    **build_pagination_meta(
                        limit=limit,
                        requested_page_size=page_size,
                        requested_max_pages=max_pages,
                        requested_page=page,
                    ),
                ),
            )
        if max_pages is not None and max_pages < 1:
            return self.error_result(
                "search",
                code="invalid_input",
                message="max_pages must be greater than or equal to 1",
                meta=self.make_meta(
                    value=query,
                    limit=limit,
                    started_at=started_at,
                    body_mode=body_mode,
                    **build_pagination_meta(
                        limit=limit,
                        requested_page_size=page_size,
                        requested_max_pages=max_pages,
                        requested_page=page,
                    ),
                ),
            )
        if page is not None and page < 1:
            return self.error_result(
                "search",
                code="invalid_input",
                message="page must be greater than or equal to 1",
                meta=self.make_meta(
                    value=query,
                    limit=limit,
                    started_at=started_at,
                    body_mode=body_mode,
                    **build_pagination_meta(
                        limit=limit,
                        requested_page_size=page_size,
                        requested_max_pages=max_pages,
                        requested_page=page,
                    ),
                ),
            )
        effective_page_size = min(max(page_size or limit, 1), _PAGE_SIZE_MAX)
        current_page = page or 1

        requests = _import_requests()
        headers = {
            "User-Agent": _UA,
            "Accept": "application/json",
        }
        qiita_token = self.runtime_env().get("QIITA_TOKEN")
        if qiita_token:
            headers["Authorization"] = f"Bearer {qiita_token}"

        items: list[NormalizedItem] = []
        raw_output: list[dict] = []
        pages_fetched = 0
        has_more: bool | None = False
        next_page: int | None = None
        total_count: str | None = None

        while len(items) < limit and (max_pages is None or pages_fetched < max_pages):
            remaining = limit - len(items)
            request_page_size = min(effective_page_size, remaining)
            try:
                response = requests.get(
                    _ITEMS_API,
                    params={
                        "query": query,
                        "page": str(current_page),
                        "per_page": str(request_page_size),
                    },
                    headers=headers,
                    timeout=30,
                )
            except requests.RequestException as exc:
                return self.error_result(
                    "search",
                    code="http_error",
                    message=f"Qiita search failed: {exc}",
                    meta=self.make_meta(
                        value=query,
                        limit=limit,
                        started_at=started_at,
                        body_mode=body_mode,
                        **build_pagination_meta(
                            limit=limit,
                            requested_page_size=page_size,
                            requested_max_pages=max_pages,
                            requested_page=page,
                        ),
                    ),
                )

            total_count = response.headers.get("Total-Count")
            if response.status_code >= 400:
                return self.error_result(
                    "search",
                    code="http_error",
                    message=f"Qiita search returned HTTP {response.status_code}",
                    raw=response.text,
                    meta=self.make_meta(
                        value=query,
                        limit=limit,
                        started_at=started_at,
                        total_count=total_count,
                        body_mode=body_mode,
                        **build_pagination_meta(
                            limit=limit,
                            requested_page_size=page_size,
                            requested_max_pages=max_pages,
                            requested_page=page,
                        ),
                    ),
                )

            try:
                raw_page = response.json()
            except ValueError:
                return self.error_result(
                    "search",
                    code="invalid_response",
                    message="Qiita search returned a non-JSON payload",
                    raw=response.text,
                    meta=self.make_meta(
                        value=query,
                        limit=limit,
                        started_at=started_at,
                        body_mode=body_mode,
                        **build_pagination_meta(
                            limit=limit,
                            requested_page_size=page_size,
                            requested_max_pages=max_pages,
                            requested_page=page,
                        ),
                    ),
                )

            if not isinstance(raw_page, list):
                return self.error_result(
                    "search",
                    code="invalid_response",
                    message="Qiita search payload was not a list",
                    raw=raw_page,
                    meta=self.make_meta(
                        value=query,
                        limit=limit,
                        started_at=started_at,
                        body_mode=body_mode,
                        **build_pagination_meta(
                            limit=limit,
                            requested_page_size=page_size,
                            requested_max_pages=max_pages,
                            requested_page=page,
                        ),
                    ),
                )

            pages_fetched += 1
            for idx, entry in enumerate(raw_page, start=len(items)):
                published_at = parse_timestamp(entry.get("created_at") or entry.get("updated_at"))
                media_references = _media_references_for_entry(entry, body_mode)
                items.append(
                    build_item(
                        item_id=entry.get("id") or f"qiita-{idx}",
                        kind="article",
                        title=entry.get("title"),
                        url=entry.get("url"),
                        text=_body_for_mode(entry.get("body"), body_mode),
                        author=(entry.get("user") or {}).get("id"),
                        published_at=published_at,
                        source=self.channel,
                        extras={
                            "likes_count": entry.get("likes_count"),
                            "stocks_count": entry.get("stocks_count"),
                            "comments_count": entry.get("comments_count"),
                            "reactions_count": entry.get("reactions_count"),
                            "page_views_count": entry.get("page_views_count"),
                            "private": entry.get("private"),
                            "tags": [tag.get("name") for tag in entry.get("tags") or [] if tag.get("name")],
                            "updated_at": parse_timestamp(entry.get("updated_at")),
                            "media_references": media_references,
                            "source_hints": article_source_hints(published_at),
                        },
                    )
                )
                raw_output.append(_entry_for_body_mode(entry, body_mode))

            absolute_consumed = ((current_page - 1) * effective_page_size) + len(raw_page)
            has_more = _has_more(total_count, absolute_consumed)
            if not has_more and len(raw_page) == request_page_size and total_count is None:
                has_more = True
            next_page = current_page + 1 if has_more else None
            if not has_more or len(items) >= limit:
                break
            current_page += 1

        return self.ok_result(
            "search",
            items=items,
            raw=raw_output,
            meta=self.make_meta(
                value=query,
                limit=limit,
                started_at=started_at,
                total_count=total_count,
                body_mode=body_mode,
                **build_pagination_meta(
                    limit=limit,
                    requested_page_size=page_size,
                    requested_max_pages=max_pages,
                    requested_page=page,
                    page_size=effective_page_size,
                    pages_fetched=pages_fetched,
                    next_page=next_page,
                    has_more=has_more,
                    total_available=total_count,
                ),
            ),
        )


def _body_for_mode(body: object, body_mode: str) -> str | None:
    if body is None:
        return None
    text = str(body)
    if body_mode == "none":
        return None
    if body_mode == "snippet":
        return text[:_BODY_SNIPPET_CHARS]
    return text


def _entry_for_body_mode(entry: dict, body_mode: str) -> dict:
    if body_mode == "full":
        return entry
    output = dict(entry)
    if body_mode == "none":
        output.pop("body", None)
    elif body_mode == "snippet" and "body" in output:
        output["body"] = _body_for_mode(output.get("body"), body_mode)
    return output


def _media_references_for_entry(entry: dict, body_mode: str) -> list[dict]:
    raw_user = entry.get("user")
    user = raw_user if isinstance(raw_user, dict) else {}
    body = _body_for_mode(entry.get("body"), body_mode)
    references = [
        reference
        for reference in [
            build_media_reference(
                type="image",
                url=user.get("profile_image_url"),
                relation="avatar",
                source_field="user.profile_image_url",
            )
        ]
        if reference is not None
    ]
    for image_url in extract_image_urls(body):
        reference = build_media_reference(
            type="image",
            url=image_url,
            relation="body_image",
            source_field="body",
        )
        if reference is not None:
            references.append(reference)
    return dedupe_media_references(references)


def _has_more(total_count: str | int | None, seen_count: int) -> bool | None:
    if total_count is None:
        return None
    try:
        return int(total_count) > seen_count
    except (TypeError, ValueError):
        return None

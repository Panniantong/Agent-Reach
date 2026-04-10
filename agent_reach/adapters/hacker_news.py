# -*- coding: utf-8 -*-
"""Hacker News collection adapter."""

from __future__ import annotations

import html
import re
import time
import warnings
from typing import cast
from urllib.parse import urlparse

from agent_reach.results import (
    CollectionResult,
    NormalizedItem,
    build_item,
    build_pagination_meta,
    parse_timestamp,
)
from agent_reach.source_hints import forum_post_source_hints, search_result_source_hints

from .base import BaseAdapter

_UA = "agent-reach/1.6.0 (+https://github.com/iwachacha/Agent-Reach)"
_FIREBASE_BASE = "https://hacker-news.firebaseio.com/v0"
_ALGOLIA_BASE = "https://hn.algolia.com/api/v1"
_LIST_ENDPOINTS = {
    "top": "topstories",
    "new": "newstories",
    "best": "beststories",
    "ask": "askstories",
    "show": "showstories",
    "job": "jobstories",
}
_HN_ITEM_RE = re.compile(r"(?:news\.ycombinator\.com/item\?id=|^item[:/])(?P<id>\d+)", re.I)


def _import_requests():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"urllib3 .* doesn't match a supported version!",
        )
        import requests

    return requests


def _strip_html(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = re.sub(r"<p\s*/?>", "\n\n", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).strip()
    return text or None


def _normalize_item_id(value: str) -> str:
    text = value.strip()
    match = _HN_ITEM_RE.search(text)
    if match:
        return match.group("id")
    parsed = urlparse(text)
    if parsed.netloc.lower() == "news.ycombinator.com":
        query = parsed.query.split("&")
        for part in query:
            if part.startswith("id=") and part[3:].isdigit():
                return part[3:]
    if text.startswith("hn:"):
        text = text[3:]
    if text.isdigit():
        return text
    return text


def _item_url(item_id: object) -> str | None:
    if item_id is None:
        return None
    return f"https://news.ycombinator.com/item?id={item_id}"


def _firebase_item(raw: dict, idx: int, *, source: str) -> NormalizedItem:
    item_id = str(raw.get("id") or f"hacker-news-{idx}")
    published_at = parse_timestamp(raw.get("time"))
    return build_item(
        item_id=item_id,
        kind=f"hacker_news_{raw.get('type') or 'item'}",
        title=raw.get("title") or f"Hacker News item {item_id}",
        url=raw.get("url") or _item_url(item_id),
        text=_strip_html(raw.get("text")),
        author=raw.get("by"),
        published_at=published_at,
        source=source,
        extras={
            "hn_url": _item_url(item_id),
            "type": raw.get("type"),
            "score": raw.get("score"),
            "descendants": raw.get("descendants"),
            "parent": raw.get("parent"),
            "kids": raw.get("kids") or [],
            "deleted": raw.get("deleted"),
            "dead": raw.get("dead"),
            "source_hints": forum_post_source_hints(published_at),
        },
    )


def _algolia_item(hit: dict, idx: int, *, source: str) -> NormalizedItem:
    item_id = str(hit.get("objectID") or hit.get("story_id") or f"hn-search-{idx}")
    published_at = parse_timestamp(hit.get("created_at") or hit.get("created_at_i"))
    title = hit.get("title") or hit.get("story_title") or f"Hacker News item {item_id}"
    return build_item(
        item_id=item_id,
        kind="hacker_news_search_result",
        title=title,
        url=hit.get("url") or hit.get("story_url") or _item_url(item_id),
        text=_strip_html(hit.get("story_text") or hit.get("comment_text")),
        author=hit.get("author"),
        published_at=published_at,
        source=source,
        extras={
            "hn_url": _item_url(item_id),
            "points": hit.get("points"),
            "num_comments": hit.get("num_comments"),
            "story_id": hit.get("story_id"),
            "tags": hit.get("_tags") or [],
            "source_hints": search_result_source_hints(published_at),
        },
    )


def _is_error_result(value: object) -> bool:
    return isinstance(value, dict) and value.get("ok") is False and "error" in value


class HackerNewsAdapter(BaseAdapter):
    """Read Hacker News through the public HN and HN Algolia APIs."""

    channel = "hacker_news"
    operations = ("search", "read", "top", "new", "best", "ask", "show", "job")

    def search(self, query: str, limit: int = 10) -> CollectionResult:
        started_at = time.perf_counter()
        requests = _import_requests()
        try:
            response = requests.get(
                f"{_ALGOLIA_BASE}/search",
                params={"query": query, "tags": "story", "hitsPerPage": limit, "page": 0},
                headers={"User-Agent": _UA, "Accept": "application/json"},
                timeout=30,
            )
        except requests.RequestException as exc:
            return self.error_result(
                "search",
                code="http_error",
                message=f"Hacker News search failed: {exc}",
                meta=self.make_meta(value=query, limit=limit, started_at=started_at),
            )

        if response.status_code >= 400:
            return self.error_result(
                "search",
                code="http_error",
                message=f"Hacker News search returned HTTP {response.status_code}",
                raw=response.text,
                meta=self.make_meta(value=query, limit=limit, started_at=started_at),
            )

        try:
            raw = response.json()
        except ValueError:
            return self.error_result(
                "search",
                code="invalid_response",
                message="Hacker News search returned a non-JSON payload",
                raw=response.text,
                meta=self.make_meta(value=query, limit=limit, started_at=started_at),
            )
        if not isinstance(raw, dict) or not isinstance(raw.get("hits"), list):
            return self.error_result(
                "search",
                code="invalid_response",
                message="Hacker News search payload did not include a hits list",
                raw=raw,
                meta=self.make_meta(value=query, limit=limit, started_at=started_at),
            )

        hits = [hit for hit in raw["hits"] if isinstance(hit, dict)]
        items = [_algolia_item(hit, idx, source=self.channel) for idx, hit in enumerate(hits[:limit])]
        return self.ok_result(
            "search",
            items=items,
            raw=raw,
            meta=self.make_meta(
                value=query,
                limit=limit,
                started_at=started_at,
                backend="hn_algolia",
                **build_pagination_meta(
                    limit=limit,
                    page_size=int(raw.get("hitsPerPage") or len(hits)),
                    pages_fetched=1,
                    has_more=bool(raw.get("nbPages") and int(raw.get("nbPages") or 0) > 1),
                    total_available=raw.get("nbHits"),
                ),
            ),
        )

    def read(self, item_id_or_url: str, limit: int | None = None) -> CollectionResult:
        started_at = time.perf_counter()
        item_id = _normalize_item_id(item_id_or_url)
        raw = self._fetch_item(item_id, operation="read", value=item_id_or_url, started_at=started_at)
        if _is_error_result(raw):
            return cast(CollectionResult, raw)
        raw_item = cast(dict, raw)
        item = _firebase_item(raw_item, 0, source=self.channel)
        return self.ok_result(
            "read",
            items=[item],
            raw=raw,
            meta=self.make_meta(
                value=item_id,
                limit=limit,
                started_at=started_at,
                backend="hacker_news_firebase",
                **build_pagination_meta(limit=limit, page_size=1, pages_fetched=1, has_more=False),
            ),
        )

    def top(self, value: str = "", limit: int = 10) -> CollectionResult:
        return self._story_list("top", value=value, limit=limit)

    def new(self, value: str = "", limit: int = 10) -> CollectionResult:
        return self._story_list("new", value=value, limit=limit)

    def best(self, value: str = "", limit: int = 10) -> CollectionResult:
        return self._story_list("best", value=value, limit=limit)

    def ask(self, value: str = "", limit: int = 10) -> CollectionResult:
        return self._story_list("ask", value=value, limit=limit)

    def show(self, value: str = "", limit: int = 10) -> CollectionResult:
        return self._story_list("show", value=value, limit=limit)

    def job(self, value: str = "", limit: int = 10) -> CollectionResult:
        return self._story_list("job", value=value, limit=limit)

    def _story_list(self, operation: str, *, value: str, limit: int) -> CollectionResult:
        started_at = time.perf_counter()
        requests = _import_requests()
        endpoint = _LIST_ENDPOINTS[operation]
        try:
            response = requests.get(
                f"{_FIREBASE_BASE}/{endpoint}.json",
                params={"print": "pretty"},
                headers={"User-Agent": _UA, "Accept": "application/json"},
                timeout=30,
            )
        except requests.RequestException as exc:
            return self.error_result(
                operation,
                code="http_error",
                message=f"Hacker News {operation} failed: {exc}",
                meta=self.make_meta(value=value or operation, limit=limit, started_at=started_at),
            )

        if response.status_code >= 400:
            return self.error_result(
                operation,
                code="http_error",
                message=f"Hacker News {operation} returned HTTP {response.status_code}",
                raw=response.text,
                meta=self.make_meta(value=value or operation, limit=limit, started_at=started_at),
            )
        try:
            raw_ids = response.json()
        except ValueError:
            return self.error_result(
                operation,
                code="invalid_response",
                message=f"Hacker News {operation} returned a non-JSON payload",
                raw=response.text,
                meta=self.make_meta(value=value or operation, limit=limit, started_at=started_at),
            )
        if not isinstance(raw_ids, list):
            return self.error_result(
                operation,
                code="invalid_response",
                message=f"Hacker News {operation} payload was not a list",
                raw=raw_ids,
                meta=self.make_meta(value=value or operation, limit=limit, started_at=started_at),
            )

        raw_items: list[dict] = []
        errors: list[dict[str, object]] = []
        for item_id in raw_ids[:limit]:
            item = self._fetch_item(str(item_id), operation=operation, value=value or operation, started_at=started_at)
            if _is_error_result(item):
                errors.append({"item_id": item_id, "error": cast(CollectionResult, item).get("error")})
            else:
                raw_items.append(cast(dict, item))

        items = [
            _firebase_item(item, idx, source=self.channel)
            for idx, item in enumerate(raw_items)
        ]
        return self.ok_result(
            operation,
            items=items,
            raw={"ids": raw_ids, "items": raw_items, "item_errors": errors},
            meta=self.make_meta(
                value=value or operation,
                limit=limit,
                started_at=started_at,
                backend="hacker_news_firebase",
                item_errors=len(errors),
                **build_pagination_meta(
                    limit=limit,
                    page_size=len(raw_ids),
                    pages_fetched=1,
                    has_more=len(raw_ids) > limit,
                    total_available=len(raw_ids),
                ),
            ),
        )

    def _fetch_item(
        self,
        item_id: str,
        *,
        operation: str,
        value: str,
        started_at: float,
    ) -> dict | CollectionResult:
        if not str(item_id).isdigit():
            return self.error_result(
                operation,
                code="invalid_input",
                message="Hacker News item input must be an item id or news.ycombinator.com item URL",
                meta=self.make_meta(value=value, started_at=started_at),
            )
        requests = _import_requests()
        try:
            response = requests.get(
                f"{_FIREBASE_BASE}/item/{item_id}.json",
                params={"print": "pretty"},
                headers={"User-Agent": _UA, "Accept": "application/json"},
                timeout=30,
            )
        except requests.RequestException as exc:
            return self.error_result(
                operation,
                code="http_error",
                message=f"Hacker News item read failed: {exc}",
                meta=self.make_meta(value=value, started_at=started_at),
            )

        if response.status_code == 404:
            return self.error_result(
                operation,
                code="not_found",
                message=f"Hacker News item not found: {item_id}",
                raw=response.text,
                meta=self.make_meta(value=value, started_at=started_at),
            )
        if response.status_code >= 400:
            return self.error_result(
                operation,
                code="http_error",
                message=f"Hacker News item read returned HTTP {response.status_code}",
                raw=response.text,
                meta=self.make_meta(value=value, started_at=started_at),
            )
        try:
            raw = response.json()
        except ValueError:
            return self.error_result(
                operation,
                code="invalid_response",
                message="Hacker News item read returned a non-JSON payload",
                raw=response.text,
                meta=self.make_meta(value=value, started_at=started_at),
            )
        if raw is None:
            return self.error_result(
                operation,
                code="not_found",
                message=f"Hacker News item not found: {item_id}",
                raw=raw,
                meta=self.make_meta(value=value, started_at=started_at),
            )
        if not isinstance(raw, dict):
            return self.error_result(
                operation,
                code="invalid_response",
                message="Hacker News item read returned an unexpected payload",
                raw=raw,
                meta=self.make_meta(value=value, started_at=started_at),
            )
        return raw

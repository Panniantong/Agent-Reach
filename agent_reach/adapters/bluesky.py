# -*- coding: utf-8 -*-
"""Bluesky collection adapter."""

from __future__ import annotations

import time
import warnings
from typing import Any
from urllib.parse import urlencode

from agent_reach.media_references import build_media_reference, dedupe_media_references
from agent_reach.results import (
    CollectionResult,
    NormalizedItem,
    build_item,
    build_pagination_meta,
    derive_title_from_text,
    parse_timestamp,
)
from agent_reach.source_hints import bluesky_source_hints

from .base import BaseAdapter

_UA = "agent-reach"
_SEARCH_HOSTS = (
    "https://public.api.bsky.app",
    "https://api.bsky.app",
)
_PAGE_SIZE_MAX = 100


def _excerpt(value: str, limit: int = 200) -> str:
    """Keep upstream failure details useful without bloating JSON output."""

    return value[:limit]


def _import_requests():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"urllib3 .* doesn't match a supported version!",
        )
        import requests

    return requests


def _post_url(post: dict) -> str | None:
    author = post.get("author") or {}
    handle = author.get("handle")
    uri = post.get("uri") or ""
    rkey = uri.rstrip("/").split("/")[-1] if uri else None
    if handle and rkey:
        return f"https://bsky.app/profile/{handle}/post/{rkey}"
    return None


def _aspect_ratio(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    width = value.get("width")
    height = value.get("height")
    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
        return None
    if width <= 0 or height <= 0:
        return None
    return {
        "width": int(width),
        "height": int(height),
    }


def _media_from_embed(embed: Any) -> list[dict[str, Any]]:
    if not isinstance(embed, dict):
        return []

    media: list[dict[str, Any]] = []
    embed_type = str(embed.get("$type") or "")

    if embed_type.endswith("images#view"):
        for image in embed.get("images") or []:
            if not isinstance(image, dict):
                continue
            media.append(
                {
                    "type": "image",
                    "url": image.get("fullsize"),
                    "thumb_url": image.get("thumb"),
                    "alt": image.get("alt"),
                    "aspect_ratio": _aspect_ratio(image.get("aspectRatio")),
                }
            )

    if embed_type.endswith("video#view"):
        media.append(
            {
                "type": "video",
                "playlist_url": embed.get("playlist"),
                "thumb_url": embed.get("thumbnail"),
                "alt": embed.get("alt"),
                "aspect_ratio": _aspect_ratio(embed.get("aspectRatio")),
            }
        )

    nested_media = embed.get("media")
    if nested_media:
        media.extend(_media_from_embed(nested_media))
    return media


def _media_references_from_media(media: list[dict[str, Any]]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for entry in media:
        if not isinstance(entry, dict):
            continue
        media_type = str(entry.get("type") or "")
        normalized_type = "video" if media_type == "video" else "image"
        reference = build_media_reference(
            type=normalized_type,
            media_type=media_type or None,
            url=entry.get("url") or entry.get("playlist_url"),
            relation="embed_media",
            thumb_url=entry.get("thumb_url"),
            alt=entry.get("alt"),
            width=(entry.get("aspect_ratio") or {}).get("width"),
            height=(entry.get("aspect_ratio") or {}).get("height"),
            source_field="embed.media",
        )
        if reference is not None:
            references.append(reference)
    return dedupe_media_references(references)


class BlueskyAdapter(BaseAdapter):
    """Search public Bluesky posts through the AppView API."""

    channel = "bluesky"
    operations = ("search",)

    def search(
        self,
        query: str,
        limit: int = 10,
        page_size: int | None = None,
        max_pages: int | None = None,
        cursor: str | None = None,
    ) -> CollectionResult:
        started_at = time.perf_counter()
        if page_size is not None and page_size < 1:
            return self.error_result(
                "search",
                code="invalid_input",
                message="page_size must be greater than or equal to 1",
                meta=self.make_meta(
                    value=query,
                    limit=limit,
                    started_at=started_at,
                    **build_pagination_meta(
                        limit=limit,
                        requested_page_size=page_size,
                        requested_max_pages=max_pages,
                        requested_cursor=cursor,
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
                    **build_pagination_meta(
                        limit=limit,
                        requested_page_size=page_size,
                        requested_max_pages=max_pages,
                        requested_cursor=cursor,
                    ),
                ),
            )

        requests = _import_requests()
        effective_page_size = min(max(page_size or limit, 1), _PAGE_SIZE_MAX)
        headers = {"User-Agent": _UA, "Accept": "application/json"}
        attempts: list[dict[str, Any]] = []
        last_error: tuple[str, str, object | None, dict[str, Any] | None] | None = None

        for index, base_url in enumerate(_SEARCH_HOSTS):
            items: list[NormalizedItem] = []
            raw_posts: list[dict[str, Any]] = []
            pages_fetched = 0
            next_cursor = cursor
            has_more: bool | None = False
            host_error: tuple[str, str, object | None, dict[str, Any] | None] | None = None

            while len(items) < limit and (max_pages is None or pages_fetched < max_pages):
                remaining = limit - len(items)
                request_page_size = min(effective_page_size, remaining)
                params = {"q": query, "limit": str(request_page_size)}
                if next_cursor:
                    params["cursor"] = next_cursor
                url = f"{base_url}/xrpc/app.bsky.feed.searchPosts?{urlencode(params)}"
                try:
                    response = requests.get(url, headers=headers, timeout=30)
                except requests.RequestException as exc:
                    attempts.append(
                        {
                            "api_base_url": base_url,
                            "error": "request_exception",
                            "reason": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
                    host_error = (
                        "http_error",
                        f"Bluesky search failed at {base_url}: {exc}",
                        None,
                        {"attempts": list(attempts)},
                    )
                    last_error = host_error
                    break

                raw_text = response.text
                if response.status_code >= 400:
                    attempts.append(
                        {
                            "api_base_url": base_url,
                            "http_status": response.status_code,
                            "reason": f"http_{response.status_code}",
                            "body_excerpt": _excerpt(raw_text),
                        }
                    )
                    host_error = (
                        "http_error",
                        f"Bluesky search returned HTTP {response.status_code} from {base_url}",
                        raw_text,
                        {"attempts": list(attempts)},
                    )
                    last_error = host_error
                    break

                try:
                    raw_page = response.json()
                except ValueError:
                    attempts.append(
                        {
                            "api_base_url": base_url,
                            "error": "invalid_json",
                            "reason": "invalid_json",
                            "body_excerpt": _excerpt(raw_text),
                        }
                    )
                    host_error = (
                        "invalid_response",
                        f"Bluesky search returned a non-JSON payload from {base_url}",
                        raw_text,
                        {"attempts": list(attempts)},
                    )
                    last_error = host_error
                    break

                posts = raw_page.get("posts")
                if not isinstance(posts, list):
                    return self.error_result(
                        "search",
                        code="invalid_response",
                        message=f"Bluesky search payload from {base_url} did not include a posts list",
                        raw=raw_page,
                        meta=self.make_meta(
                            value=query,
                            limit=limit,
                            started_at=started_at,
                            api_base_url=base_url,
                            fallback_used=index > 0,
                            **build_pagination_meta(
                                limit=limit,
                                requested_page_size=page_size,
                                requested_max_pages=max_pages,
                                requested_cursor=cursor,
                            ),
                        ),
                        details={"attempts": list(attempts)},
                    )

                pages_fetched += 1
                attempts.append(
                    {
                        "api_base_url": base_url,
                        "http_status": response.status_code,
                        "reason": "ok",
                        "post_count": len(posts),
                    }
                )
                for idx, post in enumerate(posts, start=len(items)):
                    author = post.get("author") or {}
                    record = post.get("record") or {}
                    embed = post.get("embed") or {}
                    external = (embed.get("external") or {}) if isinstance(embed, dict) else {}
                    media = _media_from_embed(embed)
                    title = derive_title_from_text(
                        record.get("text"),
                        fallback=external.get("title") or f"Bluesky post {idx + 1}",
                    )
                    published_at = parse_timestamp(record.get("createdAt") or post.get("indexedAt"))
                    items.append(
                        build_item(
                            item_id=post.get("uri") or post.get("cid") or f"bluesky-{idx}",
                            kind="post",
                            title=title,
                            url=_post_url(post),
                            text=record.get("text"),
                            author=author.get("handle"),
                            published_at=published_at,
                            source=self.channel,
                            extras={
                                "author_display_name": author.get("displayName"),
                                "like_count": post.get("likeCount"),
                                "reply_count": post.get("replyCount"),
                                "repost_count": post.get("repostCount"),
                                "quote_count": post.get("quoteCount"),
                                "bookmark_count": post.get("bookmarkCount"),
                                "labels": post.get("labels") or [],
                                "media": media,
                                "media_references": _media_references_from_media(media),
                                "external_uri": external.get("uri"),
                                "external_title": external.get("title"),
                                "source_hints": bluesky_source_hints(published_at),
                            },
                        )
                    )
                raw_posts.extend(post for post in posts if isinstance(post, dict))
                next_cursor = raw_page.get("cursor")
                has_more = bool(next_cursor) if next_cursor is not None else None
                if not has_more or len(items) >= limit:
                    break

            if host_error is not None and pages_fetched > 0:
                code, message, raw, details = host_error
                return self.ok_result(
                    "search",
                    items=items,
                    raw={"posts": raw_posts, "cursor": next_cursor},
                    meta=self.make_meta(
                        value=query,
                        limit=limit,
                        started_at=started_at,
                        api_base_url=base_url,
                        fallback_used=index > 0,
                        attempted_hosts=[attempt["api_base_url"] for attempt in attempts],
                        attempted_host_results=list(attempts),
                        pagination_interrupted={"code": code, "message": message},
                        **build_pagination_meta(
                            limit=limit,
                            requested_page_size=page_size,
                            requested_max_pages=max_pages,
                            requested_cursor=cursor,
                            page_size=effective_page_size,
                            pages_fetched=pages_fetched,
                            next_cursor=next_cursor,
                            has_more=has_more,
                        ),
                    ),
                )

            if pages_fetched > 0:
                return self.ok_result(
                    "search",
                    items=items,
                    raw={"posts": raw_posts, "cursor": next_cursor},
                    meta=self.make_meta(
                        value=query,
                        limit=limit,
                        started_at=started_at,
                        api_base_url=base_url,
                        fallback_used=index > 0,
                        attempted_hosts=[attempt["api_base_url"] for attempt in attempts],
                        attempted_host_results=list(attempts),
                        **build_pagination_meta(
                            limit=limit,
                            requested_page_size=page_size,
                            requested_max_pages=max_pages,
                            requested_cursor=cursor,
                            page_size=effective_page_size,
                            pages_fetched=pages_fetched,
                            next_cursor=next_cursor,
                            has_more=has_more,
                        ),
                    ),
                )

        if last_error is None:
            return self.error_result(
                "search",
                code="http_error",
                message="Bluesky search failed before any request could complete",
                meta=self.make_meta(
                    value=query,
                    limit=limit,
                    started_at=started_at,
                    **build_pagination_meta(
                        limit=limit,
                        requested_page_size=page_size,
                        requested_max_pages=max_pages,
                        requested_cursor=cursor,
                    ),
                ),
            )

        code, message, raw, details = last_error
        return self.error_result(
            "search",
            code=code,
            message=message,
            raw=raw,
            meta=self.make_meta(
                value=query,
                limit=limit,
                started_at=started_at,
                **build_pagination_meta(
                    limit=limit,
                    requested_page_size=page_size,
                    requested_max_pages=max_pages,
                    requested_cursor=cursor,
                ),
            ),
            details=details,
        )

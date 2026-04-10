# -*- coding: utf-8 -*-
"""Reddit collection adapter."""

from __future__ import annotations

import re
import time
import warnings
from typing import Any, cast
from urllib.parse import urlparse

from agent_reach.results import (
    CollectionResult,
    NormalizedItem,
    build_item,
    build_pagination_meta,
    derive_title_from_text,
    parse_timestamp,
)
from agent_reach.source_hints import forum_post_source_hints

from .base import BaseAdapter

_OAUTH_BASE = "https://oauth.reddit.com"
_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_SUBREDDIT_QUERY_RE = re.compile(r"^(?:r/|subreddit:)(?P<subreddit>[A-Za-z0-9_]+)\s+(?P<query>.+)$")
_COMMENTS_ID_RE = re.compile(r"(?:/comments/|^t3_|^post[:/])(?P<id>[A-Za-z0-9_]+)", re.I)


def _import_requests():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"urllib3 .* doesn't match a supported version!",
        )
        import requests

    return requests


def _permalink_url(permalink: object) -> str | None:
    if not permalink:
        return None
    text = str(permalink)
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return f"https://www.reddit.com{text}"


def _normalize_post_id(value: str) -> str:
    text = value.strip()
    match = _COMMENTS_ID_RE.search(text)
    if match:
        return match.group("id")
    parsed = urlparse(text)
    parts = [part for part in parsed.path.split("/") if part]
    if "comments" in parts:
        idx = parts.index("comments")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    if text.startswith("reddit:"):
        text = text[7:]
    return text.removeprefix("t3_")


def _search_endpoint(query: str) -> tuple[str, str, str | None]:
    text = query.strip()
    match = _SUBREDDIT_QUERY_RE.match(text)
    if not match:
        return "/search", text, None
    subreddit = match.group("subreddit")
    return f"/r/{subreddit}/search", match.group("query").strip(), subreddit


def _post_item(data: dict, idx: int, *, source: str) -> NormalizedItem:
    item_id = str(data.get("name") or data.get("id") or f"reddit-post-{idx}")
    published_at = parse_timestamp(data.get("created_utc") or data.get("created"))
    permalink = _permalink_url(data.get("permalink"))
    return build_item(
        item_id=item_id,
        kind="reddit_post",
        title=data.get("title"),
        url=permalink,
        text=data.get("selftext") or data.get("selftext_html"),
        author=data.get("author"),
        published_at=published_at,
        source=source,
        extras={
            "subreddit": data.get("subreddit"),
            "subreddit_name_prefixed": data.get("subreddit_name_prefixed"),
            "score": data.get("score"),
            "ups": data.get("ups"),
            "num_comments": data.get("num_comments"),
            "domain": data.get("domain"),
            "external_url": data.get("url") if data.get("url") != permalink else None,
            "is_self": data.get("is_self"),
            "over_18": data.get("over_18"),
            "link_flair_text": data.get("link_flair_text"),
            "stickied": data.get("stickied"),
            "locked": data.get("locked"),
            "source_hints": forum_post_source_hints(published_at),
        },
    )


def _comment_item(data: dict, idx: int, *, source: str, post_title: str | None = None) -> NormalizedItem:
    item_id = str(data.get("name") or data.get("id") or f"reddit-comment-{idx}")
    published_at = parse_timestamp(data.get("created_utc") or data.get("created"))
    text = data.get("body") or data.get("body_html")
    return build_item(
        item_id=item_id,
        kind="reddit_comment",
        title=derive_title_from_text(text, fallback=f"Comment by {data.get('author') or 'unknown'}"),
        url=_permalink_url(data.get("permalink")),
        text=text,
        author=data.get("author"),
        published_at=published_at,
        source=source,
        extras={
            "post_title": post_title,
            "parent_id": data.get("parent_id"),
            "link_id": data.get("link_id"),
            "subreddit": data.get("subreddit"),
            "score": data.get("score"),
            "ups": data.get("ups"),
            "depth": data.get("depth"),
            "stickied": data.get("stickied"),
            "source_hints": forum_post_source_hints(published_at),
        },
    )


def _listing_children(raw: dict) -> list[dict]:
    data = raw.get("data") if isinstance(raw, dict) else {}
    raw_children = data.get("children") if isinstance(data, dict) else []
    children = raw_children if isinstance(raw_children, list) else []
    return [child for child in children if isinstance(child, dict)]


def _flatten_comment_children(children: list[dict], *, limit: int) -> list[dict]:
    flattened: list[dict] = []

    def visit(node: dict) -> None:
        if len(flattened) >= limit:
            return
        if node.get("kind") == "more":
            return
        data = node.get("data")
        if not isinstance(data, dict):
            return
        flattened.append(data)
        replies = data.get("replies")
        if isinstance(replies, dict):
            for child in _listing_children(replies):
                visit(child)

    for child in children:
        visit(child)
        if len(flattened) >= limit:
            break
    return flattened


class RedditAdapter(BaseAdapter):
    """Read Reddit search results and public threads through Reddit OAuth."""

    channel = "reddit"
    operations = ("search", "read")

    def search(self, query: str, limit: int = 10) -> CollectionResult:
        started_at = time.perf_counter()
        endpoint, search_query, subreddit = _search_endpoint(query)
        if not search_query:
            return self.error_result(
                "search",
                code="invalid_input",
                message="Reddit search input must include a query",
                meta=self.make_meta(value=query, limit=limit, started_at=started_at),
            )
        response = self._get(
            endpoint,
            operation="search",
            value=query,
            started_at=started_at,
            limit=limit,
            params={
                "q": search_query,
                "limit": limit,
                "raw_json": 1,
                **({"restrict_sr": 1} if subreddit else {}),
            },
        )
        if _is_error_result(response):
            return cast(CollectionResult, response)

        raw = self._json_response(response, operation="search", value=query, limit=limit, started_at=started_at)
        if _is_error_result(raw):
            return cast(CollectionResult, raw)
        if not isinstance(raw, dict):
            return self.error_result(
                "search",
                code="invalid_response",
                message="Reddit search payload was not a listing object",
                raw=raw,
                meta=self.make_meta(value=query, limit=limit, started_at=started_at),
            )
        raw_listing = cast(dict, raw)
        children = _listing_children(raw_listing)
        items = [
            _post_item(child.get("data") or {}, idx, source=self.channel)
            for idx, child in enumerate(children[:limit])
            if isinstance(child.get("data"), dict)
        ]
        raw_metadata = raw_listing.get("data")
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        return self.ok_result(
            "search",
            items=items,
            raw=raw_listing,
            meta=self.make_meta(
                value=query,
                limit=limit,
                started_at=started_at,
                subreddit=subreddit,
                backend="reddit_oauth",
                **build_pagination_meta(
                    limit=limit,
                    page_size=len(children),
                    pages_fetched=1,
                    next_cursor=metadata.get("after"),
                    has_more=bool(metadata.get("after")),
                ),
            ),
        )

    def read(self, post_id_or_url: str, limit: int = 20) -> CollectionResult:
        started_at = time.perf_counter()
        post_id = _normalize_post_id(post_id_or_url)
        if not post_id:
            return self.error_result(
                "read",
                code="invalid_input",
                message="Reddit read input must be a post id or comments URL",
                meta=self.make_meta(value=post_id_or_url, limit=limit, started_at=started_at),
            )
        response = self._get(
            f"/comments/{post_id}",
            operation="read",
            value=post_id,
            limit=limit,
            started_at=started_at,
            params={"limit": limit, "raw_json": 1},
        )
        if _is_error_result(response):
            return cast(CollectionResult, response)

        raw = self._json_response(response, operation="read", value=post_id, limit=limit, started_at=started_at)
        if _is_error_result(raw):
            return cast(CollectionResult, raw)
        if not isinstance(raw, list) or not raw:
            return self.error_result(
                "read",
                code="invalid_response",
                message="Reddit read payload was not a thread listing",
                raw=raw,
                meta=self.make_meta(value=post_id, limit=limit, started_at=started_at),
            )
        post_children = _listing_children(raw[0]) if isinstance(raw[0], dict) else []
        if not post_children or not isinstance(post_children[0].get("data"), dict):
            return self.error_result(
                "read",
                code="not_found",
                message=f"Reddit post not found: {post_id}",
                raw=raw,
                meta=self.make_meta(value=post_id, limit=limit, started_at=started_at),
            )
        post_data = cast(dict, post_children[0]["data"])
        post_item = _post_item(post_data, 0, source=self.channel)
        comment_children = _listing_children(raw[1]) if len(raw) > 1 and isinstance(raw[1], dict) else []
        comments = _flatten_comment_children(comment_children, limit=max(limit - 1, 0))
        comment_items = [
            _comment_item(comment, idx, source=self.channel, post_title=post_item["title"])
            for idx, comment in enumerate(comments, start=1)
        ]
        items = [post_item, *comment_items][:limit]
        return self.ok_result(
            "read",
            items=items,
            raw=raw,
            meta=self.make_meta(
                value=post_id,
                limit=limit,
                started_at=started_at,
                backend="reddit_oauth",
                comment_count=len(comment_items),
                **build_pagination_meta(
                    limit=limit,
                    page_size=len(items),
                    pages_fetched=1,
                    has_more=len(comment_children) > len(comment_items),
                ),
            ),
        )

    def _get(
        self,
        endpoint: str,
        *,
        operation: str,
        value: str,
        started_at: float,
        limit: int | None,
        params: dict[str, object],
    ) -> Any | CollectionResult:
        token_or_error = self._access_token(operation=operation, value=value, limit=limit, started_at=started_at)
        if isinstance(token_or_error, dict):
            return token_or_error
        requests = _import_requests()
        user_agent = self.config.get("reddit_user_agent")
        try:
            response = requests.get(
                f"{_OAUTH_BASE}{endpoint}",
                params=params,
                headers={
                    "Authorization": f"Bearer {token_or_error}",
                    "User-Agent": str(user_agent),
                    "Accept": "application/json",
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            return self.error_result(
                operation,
                code="http_error",
                message=f"Reddit {operation} failed: {exc}",
                meta=self.make_meta(value=value, limit=limit, started_at=started_at),
            )
        if response.status_code in {401, 403}:
            return self.error_result(
                operation,
                code="unauthorized",
                message="Reddit rejected the configured OAuth token or credentials",
                raw=response.text,
                meta=self.make_meta(value=value, limit=limit, started_at=started_at),
            )
        if response.status_code == 404:
            return self.error_result(
                operation,
                code="not_found",
                message=f"Reddit resource not found: {value}",
                raw=response.text,
                meta=self.make_meta(value=value, limit=limit, started_at=started_at),
            )
        if response.status_code >= 400:
            return self.error_result(
                operation,
                code="http_error",
                message=f"Reddit {operation} returned HTTP {response.status_code}",
                raw=response.text,
                meta=self.make_meta(value=value, limit=limit, started_at=started_at),
            )
        return response

    def _access_token(
        self,
        *,
        operation: str,
        value: str,
        limit: int | None,
        started_at: float,
    ) -> str | CollectionResult:
        user_agent = self.config.get("reddit_user_agent")
        if not user_agent:
            return self.error_result(
                operation,
                code="missing_configuration",
                message="Reddit requires a unique User-Agent. Run agent-reach configure reddit-user-agent <VALUE>",
                meta=self.make_meta(value=value, limit=limit, started_at=started_at),
            )

        configured_token = self.config.get("reddit_access_token")
        if configured_token:
            return str(configured_token)

        client_id = self.config.get("reddit_client_id")
        client_secret = self.config.get("reddit_client_secret")
        if not client_id or not client_secret:
            return self.error_result(
                operation,
                code="missing_configuration",
                message=(
                    "Reddit OAuth is not configured. Set reddit-access-token, or configure "
                    "reddit-client-id, reddit-client-secret, and reddit-user-agent."
                ),
                meta=self.make_meta(value=value, limit=limit, started_at=started_at),
            )

        requests = _import_requests()
        try:
            response = requests.post(
                _TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(str(client_id), str(client_secret)),
                headers={"User-Agent": str(user_agent), "Accept": "application/json"},
                timeout=30,
            )
        except requests.RequestException as exc:
            return self.error_result(
                operation,
                code="http_error",
                message=f"Reddit OAuth token request failed: {exc}",
                meta=self.make_meta(value=value, limit=limit, started_at=started_at),
            )

        if response.status_code in {401, 403}:
            return self.error_result(
                operation,
                code="unauthorized",
                message="Reddit rejected the configured OAuth client credentials",
                raw=response.text,
                meta=self.make_meta(value=value, limit=limit, started_at=started_at),
            )
        if response.status_code >= 400:
            return self.error_result(
                operation,
                code="http_error",
                message=f"Reddit OAuth token request returned HTTP {response.status_code}",
                raw=response.text,
                meta=self.make_meta(value=value, limit=limit, started_at=started_at),
            )
        try:
            raw = response.json()
        except ValueError:
            return self.error_result(
                operation,
                code="invalid_response",
                message="Reddit OAuth token response was not JSON",
                raw=response.text,
                meta=self.make_meta(value=value, limit=limit, started_at=started_at),
            )
        if not isinstance(raw, dict) or not raw.get("access_token"):
            return self.error_result(
                operation,
                code="invalid_response",
                message="Reddit OAuth token response did not include access_token",
                raw=raw,
                meta=self.make_meta(value=value, limit=limit, started_at=started_at),
            )
        return str(raw["access_token"])

    def _json_response(
        self,
        response,
        *,
        operation: str,
        value: str,
        limit: int | None,
        started_at: float,
    ) -> dict | list | CollectionResult:
        try:
            raw = response.json()
        except ValueError:
            return self.error_result(
                operation,
                code="invalid_response",
                message=f"Reddit {operation} returned a non-JSON payload",
                raw=response.text,
                meta=self.make_meta(value=value, limit=limit, started_at=started_at),
            )
        if not isinstance(raw, (dict, list)):
            return self.error_result(
                operation,
                code="invalid_response",
                message=f"Reddit {operation} returned an unexpected payload",
                raw=raw,
                meta=self.make_meta(value=value, limit=limit, started_at=started_at),
            )
        return raw


def _is_error_result(value: object) -> bool:
    return isinstance(value, dict) and value.get("ok") is False and "error" in value

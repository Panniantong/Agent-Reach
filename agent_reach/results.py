# -*- coding: utf-8 -*-
"""Shared result schema helpers for external collection APIs."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from time import struct_time
from typing import Any, TypedDict, cast
from urllib.parse import urlsplit, urlunsplit

from agent_reach._version import __version__
from agent_reach.schemas import SCHEMA_VERSION, utc_timestamp

_PAGINATION_FIELDS = (
    "requested_limit",
    "requested_page_size",
    "page_size",
    "requested_max_pages",
    "requested_page",
    "requested_cursor",
    "pages_fetched",
    "next_page",
    "next_cursor",
    "has_more",
    "total_available",
)

_ENGAGEMENT_FIELDS = (
    "likes",
    "reposts",
    "retweets",
    "replies",
    "quotes",
    "views",
    "bookmarks",
    "points",
    "comments",
    "stars",
    "forks",
)

_ENGAGEMENT_ALIASES = {
    "likes": ("likes", "like_count", "likes_count"),
    "reposts": ("reposts", "repost_count", "reposts_count"),
    "retweets": ("retweets", "retweet_count", "retweets_count"),
    "replies": ("replies", "reply_count", "replies_count"),
    "quotes": ("quotes", "quote_count", "quotes_count"),
    "views": ("views", "view_count", "views_count", "page_views_count"),
    "bookmarks": ("bookmarks", "bookmark_count", "bookmarks_count", "stocks_count"),
    "points": ("points", "score", "ups"),
    "comments": ("comments", "comment_count", "comments_count", "num_comments", "descendants"),
    "stars": ("stars", "star_count", "stargazer_count", "stargazers_count"),
    "forks": ("forks", "fork_count", "forks_count"),
}

_ERROR_CATEGORY_ALIASES = {
    "timeout": {"timeout", "timed_out"},
    "auth_required": {"auth_required", "not_authenticated", "not_authorized", "unauthorized", "forbidden"},
    "rate_limited": {"rate_limited", "rate_limit", "too_many_requests"},
    "dependency_missing": {"dependency_missing", "missing_dependency"},
    "invalid_input": {
        "invalid_input",
        "unknown_channel",
        "unsupported_operation",
        "unsupported_option",
        "missing_configuration",
    },
    "parse_error": {"parse_error", "parse_failed", "invalid_response", "invalid_json"},
    "no_results": {"no_results", "not_found"},
    "upstream_unavailable": {"upstream_unavailable", "http_error", "dns_error", "command_failed", "internal_error"},
}

_RETRYABLE_ERROR_CATEGORIES = {"timeout", "rate_limited", "upstream_unavailable"}
_ITEM_TEXT_MODES = {"full", "snippet", "none"}
_DEFAULT_ITEM_TEXT_SNIPPET_CHARS = 500


class NormalizedItem(TypedDict):
    """A normalized content item that can be consumed by external projects."""

    id: str
    kind: str
    title: str | None
    url: str | None
    text: str | None
    author: str | None
    published_at: str | None
    source: str
    canonical_url: str | None
    source_item_id: str | None
    engagement: dict[str, int | float]
    media_references: list[dict[str, Any]]
    identifiers: dict[str, Any]
    extras: dict[str, Any]


class CollectionError(TypedDict):
    """A stable external-facing error shape."""

    code: str
    category: str
    message: str
    details: dict[str, Any]
    retryable: bool


class CollectionResult(TypedDict):
    """A stable external-facing collection result."""

    schema_version: str
    agent_reach_version: str
    ok: bool
    channel: str
    operation: str
    items: list[NormalizedItem]
    raw: Any
    meta: dict[str, Any]
    error: CollectionError | None


def build_pagination_meta(
    *,
    limit: int | None = None,
    requested_page_size: int | None = None,
    page_size: int | None = None,
    requested_max_pages: int | None = None,
    requested_page: int | None = None,
    requested_cursor: Any = None,
    pages_fetched: int | None = None,
    next_page: int | None = None,
    next_cursor: Any = None,
    has_more: bool | None = None,
    total_available: int | str | None = None,
) -> dict[str, Any]:
    """Build standardized pagination metadata fields."""

    meta: dict[str, Any] = {}
    if limit is not None:
        meta["requested_limit"] = int(limit)
    if requested_page_size is None and page_size is not None:
        requested_page_size = page_size
    if requested_page_size is not None:
        meta["requested_page_size"] = int(requested_page_size)
    if page_size is not None:
        meta["page_size"] = int(page_size)
    if requested_max_pages is not None:
        meta["requested_max_pages"] = int(requested_max_pages)
    if requested_page is not None:
        meta["requested_page"] = int(requested_page)
    if requested_cursor is not None:
        meta["requested_cursor"] = requested_cursor
    if pages_fetched is not None:
        meta["pages_fetched"] = int(pages_fetched)
    if next_page is not None:
        meta["next_page"] = int(next_page)
    if next_cursor is not None:
        meta["next_cursor"] = next_cursor
    if has_more is not None:
        meta["has_more"] = bool(has_more)
    if total_available is not None:
        try:
            meta["total_available"] = int(total_available)
        except (TypeError, ValueError):
            meta["total_available"] = total_available
    if meta:
        meta["pagination"] = {key: meta[key] for key in _PAGINATION_FIELDS if key in meta}
    return meta


def build_item(
    *,
    item_id: str,
    kind: str,
    title: str | None,
    url: str | None,
    text: str | None,
    author: str | None,
    published_at: str | None,
    source: str,
    extras: dict[str, Any] | None = None,
    canonical_url: str | None = None,
    source_item_id: str | None = None,
    engagement: dict[str, Any] | None = None,
    media_references: list[dict[str, Any]] | None = None,
    identifiers: dict[str, Any] | None = None,
) -> NormalizedItem:
    """Build a normalized item."""

    payload_extras = extras or {}
    payload_canonical_url = canonical_url if canonical_url is not None else canonicalize_url(url)
    payload_source_item_id = source_item_id if source_item_id is not None else str(item_id)
    payload_engagement = normalize_engagement(engagement if engagement is not None else payload_extras)
    payload_media_references = _normalize_media_references(
        media_references if media_references is not None else payload_extras.get("media_references")
    )
    payload_identifiers = _normalize_identifiers(
        url=url,
        item_id=item_id,
        source=source,
        extras=payload_extras,
        identifiers=identifiers,
    )
    return {
        "id": item_id,
        "kind": kind,
        "title": title,
        "url": url,
        "text": text,
        "author": author,
        "published_at": published_at,
        "source": source,
        "canonical_url": payload_canonical_url,
        "source_item_id": payload_source_item_id,
        "engagement": payload_engagement,
        "media_references": payload_media_references,
        "identifiers": payload_identifiers,
        "extras": payload_extras,
    }


def build_result(
    *,
    ok: bool,
    channel: str,
    operation: str,
    items: list[NormalizedItem] | None = None,
    raw: Any = None,
    meta: dict[str, Any] | None = None,
    error: CollectionError | None = None,
) -> CollectionResult:
    """Build a collection result envelope."""

    item_count = len(items or [])
    payload_meta = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_timestamp(),
        **(meta or {}),
    }
    if "limit" in payload_meta and "requested_limit" not in payload_meta:
        payload_meta["requested_limit"] = payload_meta["limit"]
    if payload_meta.get("count") is None:
        payload_meta["count"] = item_count
    if payload_meta.get("returned_count") is None:
        payload_meta["returned_count"] = item_count
    _synchronize_pagination_meta(payload_meta)
    return {
        "schema_version": SCHEMA_VERSION,
        "agent_reach_version": __version__,
        "ok": ok,
        "channel": channel,
        "operation": operation,
        "items": items or [],
        "raw": raw,
        "meta": payload_meta,
        "error": error,
    }


def build_error(
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> CollectionError:
    """Build a stable collection error."""

    category = classify_error_category(code, details=details, message=message)
    return {
        "code": code,
        "category": category,
        "message": message,
        "details": details or {},
        "retryable": category in _RETRYABLE_ERROR_CATEGORIES,
    }


def canonicalize_url(url: str | None) -> str | None:
    """Return a stable URL form for evidence dedupe, without ranking semantics."""

    if not url:
        return None
    text = str(url).strip()
    if not text:
        return None
    parts = urlsplit(text)
    if not parts.scheme or not parts.netloc:
        return text
    path = parts.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            parts.query,
            "",
        )
    )


def normalize_engagement(values: dict[str, Any] | None) -> dict[str, int | float]:
    """Normalize raw source metrics into common, non-scoring engagement fields."""

    if not values:
        return {}
    raw_metrics_value = values.get("metrics")
    raw_metrics: dict[str, Any] = raw_metrics_value if isinstance(raw_metrics_value, dict) else {}
    sources: list[dict[str, Any]] = [values, raw_metrics]
    normalized: dict[str, int | float] = {}
    for field in _ENGAGEMENT_FIELDS:
        for source in sources:
            value = _first_present(source, _ENGAGEMENT_ALIASES[field])
            number = _number_or_none(value)
            if number is not None:
                normalized[field] = number
                break
    return normalized


def classify_error_category(
    code: str | None,
    *,
    details: dict[str, Any] | None = None,
    message: str | None = None,
) -> str:
    """Map source-specific error codes to a stable cross-channel taxonomy."""

    text = (code or "").strip().lower()
    for category, aliases in _ERROR_CATEGORY_ALIASES.items():
        if text in aliases:
            return category

    detail_text = " ".join(str(value).lower() for value in (details or {}).values() if value is not None)
    message_text = (message or "").lower()
    haystack = f"{text} {detail_text} {message_text}"
    if "timeout" in haystack or "timed out" in haystack:
        return "timeout"
    if "rate limit" in haystack or "too many requests" in haystack:
        return "rate_limited"
    if "auth" in haystack or "login" in haystack or "credential" in haystack:
        return "auth_required"
    return "unknown"


def apply_raw_mode(
    result: CollectionResult,
    *,
    raw_mode: str = "full",
    raw_max_bytes: int | None = None,
) -> CollectionResult:
    """Return a copy of a CollectionResult with caller-selected raw payload retention."""

    if raw_mode not in {"full", "minimal", "none"}:
        raise ValueError("raw_mode must be one of: full, minimal, none")
    if raw_max_bytes is not None and raw_max_bytes < 1:
        raise ValueError("raw_max_bytes must be greater than or equal to 1")

    payload: CollectionResult = {
        **result,
        "items": [cast(NormalizedItem, dict(item)) for item in result.get("items") or []],
        "meta": dict(result.get("meta") or {}),
    }
    raw_payload = result.get("raw")
    raw_length = _raw_payload_bytes(raw_payload)
    payload["meta"]["raw_mode"] = raw_mode
    payload["meta"]["raw_payload_bytes"] = raw_length

    if raw_mode == "none":
        payload["raw"] = None
        payload["meta"]["raw_payload_omitted"] = True
        return payload

    if raw_mode == "minimal":
        payload["raw"] = _raw_minimal_summary(raw_payload, raw_length)
        payload["meta"]["raw_payload_minimized"] = True
        return payload

    if raw_max_bytes is not None and raw_length > raw_max_bytes:
        payload["raw"] = _raw_truncation_summary(raw_payload, raw_length, raw_max_bytes)
        payload["meta"]["raw_payload_truncated"] = True
        payload["meta"]["raw_max_bytes"] = raw_max_bytes
        return payload

    return payload


def apply_item_text_mode(
    result: CollectionResult,
    *,
    item_text_mode: str = "full",
    item_text_max_chars: int | None = None,
) -> CollectionResult:
    """Return a copy of a CollectionResult with caller-selected item text retention."""

    if item_text_mode not in _ITEM_TEXT_MODES:
        raise ValueError("item_text_mode must be one of: full, snippet, none")
    if item_text_max_chars is not None and item_text_max_chars < 1:
        raise ValueError("item_text_max_chars must be greater than or equal to 1")

    payload: CollectionResult = {
        **result,
        "items": [cast(NormalizedItem, dict(item)) for item in result.get("items") or []],
        "meta": dict(result.get("meta") or {}),
    }
    payload["meta"]["item_text_mode"] = item_text_mode

    if item_text_mode == "full":
        return payload

    max_chars = item_text_max_chars or _DEFAULT_ITEM_TEXT_SNIPPET_CHARS
    if item_text_mode == "snippet":
        payload["meta"]["item_text_max_chars"] = max_chars

    for item in payload["items"]:
        text = item.get("text")
        if text is None:
            continue
        if item_text_mode == "none":
            item["text"] = None
            continue
        item["text"] = str(text)[:max_chars]

    return payload


def _normalize_media_references(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _normalize_identifiers(
    *,
    url: str | None,
    item_id: str,
    source: str,
    extras: dict[str, Any],
    identifiers: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    if identifiers:
        normalized.update({str(key): value for key, value in identifiers.items() if value not in (None, "", [], {})})
    domain = _domain_from_url(url)
    if domain:
        normalized.setdefault("domain", domain)
    repo_full_name = extras.get("repo_full_name")
    if repo_full_name:
        normalized.setdefault("repo_full_name", repo_full_name)
    elif source == "github" and "/" in str(item_id):
        normalized.setdefault("repo_full_name", str(item_id))
    return normalized


def _domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(str(url))
    return parsed.netloc.lower() or None


def _first_present(values: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in values and values[key] is not None:
            return values[key]
    return None


def _number_or_none(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        return int(number) if number.is_integer() else number
    return None


def _raw_payload_bytes(raw_payload: Any) -> int:
    if raw_payload is None:
        return 0
    if isinstance(raw_payload, str):
        return len(raw_payload.encode("utf-8", errors="replace"))
    try:
        return len(json_dumps(raw_payload).encode("utf-8", errors="replace"))
    except (TypeError, ValueError):
        return len(str(raw_payload).encode("utf-8", errors="replace"))


def _raw_minimal_summary(raw_payload: Any, raw_length: int) -> dict[str, Any] | None:
    if raw_payload is None:
        return None
    summary: dict[str, Any] = {
        "raw_mode": "minimal",
        "type": type(raw_payload).__name__,
        "approx_bytes": raw_length,
    }
    if isinstance(raw_payload, dict):
        summary["keys"] = sorted(str(key) for key in raw_payload.keys())[:50]
    elif isinstance(raw_payload, list):
        summary["length"] = len(raw_payload)
        if raw_payload and isinstance(raw_payload[0], dict):
            summary["first_item_keys"] = sorted(str(key) for key in raw_payload[0].keys())[:50]
    elif isinstance(raw_payload, str):
        summary["preview"] = raw_payload[:500]
    return summary


def _raw_truncation_summary(raw_payload: Any, raw_length: int, raw_max_bytes: int) -> dict[str, Any]:
    if isinstance(raw_payload, str):
        preview = raw_payload.encode("utf-8", errors="replace")[:raw_max_bytes].decode("utf-8", errors="replace")
    else:
        try:
            preview = json_dumps(raw_payload)[:raw_max_bytes]
        except (TypeError, ValueError):
            preview = str(raw_payload)[:raw_max_bytes]
    return {
        "raw_mode": "truncated",
        "type": type(raw_payload).__name__,
        "approx_bytes": raw_length,
        "max_bytes": raw_max_bytes,
        "preview": preview,
    }


def json_dumps(value: Any) -> str:
    """Serialize JSON in the same compact form used for byte accounting."""

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _synchronize_pagination_meta(meta: dict[str, Any]) -> None:
    """Keep flat pagination keys and meta.pagination in sync."""

    raw_pagination = meta.get("pagination")
    pagination: dict[str, Any] = raw_pagination if isinstance(raw_pagination, dict) else {}
    for field in _PAGINATION_FIELDS:
        if field in meta and meta[field] is not None:
            pagination[field] = meta[field]
        elif field in pagination:
            meta[field] = pagination[field]
    if pagination:
        meta["pagination"] = {field: pagination[field] for field in _PAGINATION_FIELDS if field in pagination}


def parse_timestamp(value: Any) -> str | None:
    """Best-effort conversion of common timestamp shapes into ISO-8601."""

    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, struct_time):
        return datetime(*value[:6], tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
                return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            except ValueError:
                pass
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except ValueError:
            pass
        if len(text) == 8 and text.isdigit():
            try:
                parsed = datetime.strptime(text, "%Y%m%d").replace(tzinfo=timezone.utc)
                return parsed.isoformat().replace("+00:00", "Z")
            except ValueError:
                pass
        try:
            parsed = parsedate_to_datetime(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except (TypeError, ValueError):
            return text
    return str(value)


def derive_title_from_text(text: str | None, fallback: str | None = None, max_length: int = 80) -> str | None:
    """Return a compact title derived from text when a native title is unavailable."""

    if text:
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if first_line:
            return first_line[:max_length]
    return fallback

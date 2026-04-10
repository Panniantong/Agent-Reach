# -*- coding: utf-8 -*-
"""Conservative diagnostic hints for normalized collection items."""

from __future__ import annotations

from typing import TypedDict


class SourceHints(TypedDict):
    """Small, non-authoritative source diagnostics for downstream consumers."""

    source_kind: str
    authority_hint: str
    freshness_hint: str
    volatility_hint: str


def build_source_hints(
    *,
    source_kind: str,
    authority_hint: str,
    published_at: str | None,
    volatility_hint: str,
) -> SourceHints:
    """Build conservative source hints without ranking or scoring."""

    return {
        "source_kind": source_kind,
        "authority_hint": authority_hint,
        "freshness_hint": "timestamped" if published_at else "unknown",
        "volatility_hint": volatility_hint,
    }


def web_source_hints(published_at: str | None) -> SourceHints:
    return build_source_hints(
        source_kind="unknown",
        authority_hint="unknown",
        published_at=published_at,
        volatility_hint="unknown",
    )


def github_source_hints(published_at: str | None) -> SourceHints:
    return build_source_hints(
        source_kind="repository",
        authority_hint="project_owner",
        published_at=published_at,
        volatility_hint="medium",
    )


def rss_source_hints(published_at: str | None) -> SourceHints:
    return build_source_hints(
        source_kind="feed_item",
        authority_hint="unknown",
        published_at=published_at,
        volatility_hint="medium",
    )


def bluesky_source_hints(published_at: str | None) -> SourceHints:
    return build_source_hints(
        source_kind="social_post",
        authority_hint="social",
        published_at=published_at,
        volatility_hint="high",
    )


def search_result_source_hints(published_at: str | None) -> SourceHints:
    return build_source_hints(
        source_kind="search_result",
        authority_hint="search_index",
        published_at=published_at,
        volatility_hint="high",
    )


def page_source_hints(published_at: str | None) -> SourceHints:
    return build_source_hints(
        source_kind="page",
        authority_hint="unknown",
        published_at=published_at,
        volatility_hint="unknown",
    )


def registry_entry_source_hints(published_at: str | None) -> SourceHints:
    return build_source_hints(
        source_kind="registry_entry",
        authority_hint="registry",
        published_at=published_at,
        volatility_hint="medium",
    )


def forum_post_source_hints(published_at: str | None) -> SourceHints:
    return build_source_hints(
        source_kind="forum_post",
        authority_hint="community",
        published_at=published_at,
        volatility_hint="high",
    )

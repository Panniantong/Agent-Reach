# -*- coding: utf-8 -*-
"""Diagnostic extraction hygiene helpers for page-like sources."""

from __future__ import annotations

import re
from typing import Any

from agent_reach.media_references import extract_image_urls

_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)\s]+)")
_BARE_URL_RE = re.compile(r"(?<!\()https?://[^\s)]+")
_NAV_HEAVY_LINK_THRESHOLD = 25
_NAV_HEAVY_MAX_CHARS_PER_LINK = 120


def build_extraction_hygiene(text: str | None) -> dict[str, int | float | str | None]:
    """Return non-scoring diagnostics about extracted page shape."""

    normalized = text or ""
    link_count = _count_links(normalized)
    text_length = len(normalized)
    return {
        "text_length": text_length,
        "link_count": link_count,
        "image_count": _count_images(normalized),
        "link_density": round(link_count / text_length, 6) if text_length else 0.0,
        "extraction_warning": _extraction_warning(text_length, link_count),
    }


def _count_links(text: str) -> int:
    return len(_MARKDOWN_LINK_RE.findall(text)) + len(_BARE_URL_RE.findall(text))


def _count_images(text: str) -> int:
    seen: dict[str, Any] = {}
    for image_url in extract_image_urls(text):
        seen.setdefault(str(image_url), True)
    return len(seen)


def _extraction_warning(text_length: int, link_count: int) -> str | None:
    if link_count < _NAV_HEAVY_LINK_THRESHOLD:
        return None
    if text_length <= link_count * _NAV_HEAVY_MAX_CHARS_PER_LINK:
        return "navigation_heavy"
    return None

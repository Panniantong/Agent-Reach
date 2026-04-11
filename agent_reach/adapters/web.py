# -*- coding: utf-8 -*-
"""Web collection adapter."""

from __future__ import annotations

import re
import time
import warnings
from urllib.parse import urlparse

from agent_reach.extraction_hygiene import build_extraction_hygiene
from agent_reach.media_references import (
    build_media_reference,
    dedupe_media_references,
    extract_image_urls,
)
from agent_reach.results import (
    CollectionResult,
    build_item,
    derive_title_from_text,
    parse_timestamp,
)
from agent_reach.source_hints import web_source_hints

from .base import BaseAdapter

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_READER_DNS_ERROR_RE = re.compile(r"Domain '([^']+)' could not be resolved")


def _import_requests():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"urllib3 .* doesn't match a supported version!",
        )
        import requests

    return requests


def _normalize_url(url: str) -> str:
    return url if url.startswith(("http://", "https://")) else f"https://{url}"


def _extract_reader_metadata(markdown: str) -> tuple[str | None, str | None, str]:
    title_match = re.search(r"^Title:\s*(.+)$", markdown, re.MULTILINE)
    published_match = re.search(r"^Published Time:\s*(.+)$", markdown, re.MULTILINE)
    body_marker = "Markdown Content:"

    title = title_match.group(1).strip() if title_match else None
    published_at = parse_timestamp(published_match.group(1).strip()) if published_match else None
    if body_marker in markdown:
        body = markdown.split(body_marker, 1)[1].strip()
    else:
        body = markdown.strip()
    return title, published_at, body


def _title_from_markdown(url: str, markdown: str, fallback_title: str | None = None) -> str | None:
    if fallback_title:
        return fallback_title
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or derive_title_from_text(markdown, fallback=url)
    parsed = urlparse(url)
    return derive_title_from_text(markdown, fallback=parsed.netloc or url)


def _web_media_references(text: str) -> list[dict]:
    references = []
    for image_url in extract_image_urls(text):
        reference = build_media_reference(
            type="image",
            url=image_url,
            relation="page_image",
            source_field="markdown",
        )
        if reference is not None:
            references.append(reference)
    return dedupe_media_references(references)


def _reader_error_details(status_code: int, reader_url: str, response_text: str) -> tuple[str, str, dict[str, object]]:
    details: dict[str, object] = {
        "reader_url": reader_url,
        "reader_status_code": status_code,
    }
    match = _READER_DNS_ERROR_RE.search(response_text or "")
    if match:
        details["upstream_error"] = "domain_resolution_failed"
        details["unresolved_domain"] = match.group(1)
        return (
            "dns_error",
            f"Web read failed because Jina Reader could not resolve {match.group(1)}",
            details,
        )
    return "http_error", f"Web read returned HTTP {status_code}", details


class WebAdapter(BaseAdapter):
    """Read generic web pages through Jina Reader."""

    channel = "web"
    operations = ("read",)

    def read(self, url: str, limit: int | None = None) -> CollectionResult:
        started_at = time.perf_counter()
        normalized = _normalize_url(url)
        reader_url = f"https://r.jina.ai/{normalized}"
        requests = _import_requests()
        try:
            response = requests.get(
                reader_url,
                headers={"User-Agent": _UA, "Accept": "text/plain"},
                timeout=30,
            )
        except requests.RequestException as exc:
            return self.error_result(
                "read",
                code="http_error",
                message=f"Web read failed: {exc}",
                meta=self.make_meta(value=normalized, limit=limit, started_at=started_at),
            )

        status_code = int(getattr(response, "status_code", 200) or 200)
        markdown = getattr(response, "text", "")
        if status_code >= 400:
            code, message, details = _reader_error_details(status_code, reader_url, markdown)
            return self.error_result(
                "read",
                code=code,
                message=message,
                raw=markdown or None,
                meta=self.make_meta(
                    value=normalized,
                    limit=limit,
                    started_at=started_at,
                    reader_url=reader_url,
                    reader_status_code=status_code,
                ),
                details=details,
            )

        title, published_at, body = _extract_reader_metadata(markdown)
        hygiene_meta = build_extraction_hygiene(body)
        media_references = _web_media_references(body)
        item = build_item(
            item_id=normalized,
            kind="page",
            title=_title_from_markdown(normalized, body, fallback_title=title),
            url=normalized,
            text=body,
            author=None,
            published_at=published_at,
            source=self.channel,
            extras={
                "reader_url": reader_url,
                "extraction_hygiene": dict(hygiene_meta),
                "media_references": media_references,
                "source_hints": web_source_hints(published_at),
            },
        )
        return self.ok_result(
            "read",
            items=[item],
            raw=markdown,
            meta=self.make_meta(
                value=normalized,
                limit=limit,
                started_at=started_at,
                **hygiene_meta,
                extraction_hygiene=dict(hygiene_meta),
            ),
        )

# -*- coding: utf-8 -*-
"""crawl4ai-backed browser collection adapter."""

from __future__ import annotations

import asyncio
import re
import time
from types import SimpleNamespace
from typing import Iterable, cast
from urllib.parse import urlparse

from agent_reach.extraction_hygiene import build_extraction_hygiene
from agent_reach.media_references import (
    build_media_reference,
    dedupe_media_references,
    extract_image_urls,
)
from agent_reach.results import (
    CollectionResult,
    NormalizedItem,
    build_item,
    derive_title_from_text,
    parse_timestamp,
)
from agent_reach.source_hints import page_source_hints

from .base import BaseAdapter

_BROWSER_INSTALL_HINT = "python -m playwright install chromium"
_EXTRA_INSTALL_HINT = "install agent-reach[crawl4ai] in the Python environment that needs browser-backed reads"
_CHECKOUT_INSTALL_HINT = "uv pip install -e .[crawl4ai]"


def _import_crawl4ai() -> SimpleNamespace:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    from crawl4ai.deep_crawling import (
        BestFirstCrawlingStrategy,
        DomainFilter,
        FilterChain,
        KeywordRelevanceScorer,
    )

    return SimpleNamespace(
        AsyncWebCrawler=AsyncWebCrawler,
        BrowserConfig=BrowserConfig,
        CrawlerRunConfig=CrawlerRunConfig,
        BestFirstCrawlingStrategy=BestFirstCrawlingStrategy,
        DomainFilter=DomainFilter,
        FilterChain=FilterChain,
        KeywordRelevanceScorer=KeywordRelevanceScorer,
    )


def _normalize_url(url: str) -> str:
    return url if "://" in url else f"https://{url}"


def _validated_http_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return url
    return None


def _origin_key(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _same_origin(url: str | None, seed_url: str) -> bool:
    return _origin_key(url) == _origin_key(seed_url)


def _query_keywords(query: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"\w+", query, flags=re.UNICODE):
        normalized = token.strip().lower()
        if len(normalized) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(normalized)
    return tokens or [query.strip()]


def _get_value(value: object, key: str, default: object = None) -> object:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _stringish_markdown(value: object) -> str | None:
    if isinstance(value, str):
        return value or None
    if value is None:
        return None
    for attr in ("raw_markdown", "markdown", "fit_markdown", "content"):
        nested = getattr(value, attr, None)
        if isinstance(nested, str) and nested:
            return nested
    return None


def _extract_markdown(result: object) -> str | None:
    for key in ("markdown", "fit_markdown", "extracted_content", "cleaned_html"):
        value = _get_value(result, key)
        text = _stringish_markdown(value)
        if text:
            return text
    return None


def _extract_metadata(result: object) -> dict:
    metadata = _get_value(result, "metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _extract_author(metadata: dict) -> str | None:
    for key in ("author", "byline", "article:author", "twitter:creator"):
        value = metadata.get(key)
        if value:
            return str(value)
    return None


def _extract_published_at(metadata: dict) -> str | None:
    for key in (
        "published",
        "published_at",
        "publishedAt",
        "updated_at",
        "updatedAt",
        "modified",
        "datePublished",
        "article:published_time",
        "article:modified_time",
    ):
        value = metadata.get(key)
        if value:
            return parse_timestamp(value)
    return None


def _extract_title(url: str, metadata: dict, markdown: str | None) -> str | None:
    for key in ("title", "og:title", "twitter:title"):
        value = metadata.get(key)
        if value:
            return str(value)
    parsed = urlparse(url)
    return derive_title_from_text(markdown, fallback=parsed.netloc or url)


def _extract_media_references(metadata: dict, markdown: str | None) -> list[dict]:
    references = []
    for key in ("og:image", "twitter:image", "image", "thumbnail", "thumbnail_url"):
        reference = build_media_reference(
            type="image",
            url=metadata.get(key),
            relation="metadata_image",
            source_field=f"metadata.{key}",
        )
        if reference is not None:
            references.append(reference)
    for image_url in extract_image_urls(markdown):
        reference = build_media_reference(
            type="image",
            url=image_url,
            relation="page_image",
            source_field="markdown",
        )
        if reference is not None:
            references.append(reference)
    return dedupe_media_references(references)


def _result_url(result: object, fallback: str) -> str:
    return str(
        _get_value(result, "redirected_url")
        or _get_value(result, "url")
        or fallback
    )


def _normalize_page_item(result: object, *, fallback_url: str, crawl_query: str | None = None) -> NormalizedItem:
    resolved_url = _result_url(result, fallback_url)
    metadata = _extract_metadata(result)
    markdown = _extract_markdown(result)
    published_at = _extract_published_at(metadata)
    extraction_hygiene = build_extraction_hygiene(markdown)
    extras = {
        "status_code": _get_value(result, "status_code"),
        "final_url": resolved_url,
        "extraction_hygiene": extraction_hygiene,
        "media_references": _extract_media_references(metadata, markdown),
        "source_hints": page_source_hints(published_at),
    }
    if crawl_query is not None:
        extras["crawl_query"] = crawl_query

    return build_item(
        item_id=resolved_url,
        kind="page",
        title=_extract_title(resolved_url, metadata, markdown),
        url=resolved_url,
        text=markdown,
        author=_extract_author(metadata),
        published_at=published_at,
        source="crawl4ai",
        extras=extras,
    )


def _raw_page(result: object, *, fallback_url: str) -> dict:
    metadata = _extract_metadata(result)
    return {
        "url": _get_value(result, "url") or fallback_url,
        "final_url": _get_value(result, "redirected_url") or _get_value(result, "url") or fallback_url,
        "status_code": _get_value(result, "status_code"),
        "success": bool(_get_value(result, "success", True)),
        "error_message": _get_value(result, "error_message"),
        "metadata": metadata,
        "markdown": _extract_markdown(result),
    }


def _results_list(result: object) -> list[object]:
    if result is None:
        return []
    if isinstance(result, list):
        return result
    if isinstance(result, tuple):
        return list(result)
    if isinstance(result, (str, bytes, dict)):
        return [result]
    if hasattr(result, "__iter__"):
        return list(cast(Iterable[object], result))
    return [result]


def _classify_runtime_failure(exc: Exception) -> tuple[str, str]:
    message = str(exc)
    lowered = message.lower()
    if any(
        marker in lowered
        for marker in (
            "no module named",
            "please run playwright install",
            "executable doesn't exist",
            "browser type.launch",
            "playwright",
            "patchright",
        )
    ):
        return (
            "missing_dependency",
            (
                "crawl4ai is not fully installed. For external project environments, "
                f"{_EXTRA_INSTALL_HINT}; then run {_BROWSER_INSTALL_HINT}. "
                f"For checkout development, use {_CHECKOUT_INSTALL_HINT}."
            ),
        )
    return "http_error", f"crawl4ai run failed: {message}"


async def _run_read(url: str) -> object:
    bundle = _import_crawl4ai()
    browser_config = bundle.BrowserConfig(headless=True, verbose=False)
    run_config = bundle.CrawlerRunConfig(
        verbose=False,
        exclude_external_links=True,
        log_console=False,
        capture_console_messages=False,
        capture_network_requests=False,
    )
    async with bundle.AsyncWebCrawler(config=browser_config) as crawler:
        return await crawler.arun(url=url, config=run_config)


async def _run_crawl(url: str, crawl_query: str, limit: int) -> list[object]:
    bundle = _import_crawl4ai()
    browser_config = bundle.BrowserConfig(headless=True, verbose=False)
    strategy = bundle.BestFirstCrawlingStrategy(
        max_depth=2,
        filter_chain=bundle.FilterChain(
            filters=[bundle.DomainFilter(allowed_domains=[urlparse(url).netloc])]
        ),
        url_scorer=bundle.KeywordRelevanceScorer(_query_keywords(crawl_query)),
        include_external=False,
        max_pages=limit,
    )
    run_config = bundle.CrawlerRunConfig(
        verbose=False,
        stream=False,
        score_links=True,
        exclude_external_links=True,
        log_console=False,
        capture_console_messages=False,
        capture_network_requests=False,
        deep_crawl_strategy=strategy,
    )
    async with bundle.AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=run_config)
    return _results_list(result)


class Crawl4AIAdapter(BaseAdapter):
    """Browser-backed page reads and bounded crawls via crawl4ai."""

    channel = "crawl4ai"
    operations = ("read", "crawl")

    def read(self, url: str, limit: int | None = None) -> CollectionResult:
        started_at = time.perf_counter()
        normalized = _validated_http_url(_normalize_url(url))
        if normalized is None:
            return self.error_result(
                "read",
                code="invalid_input",
                message="crawl4ai read requires an http or https URL",
                meta=self.make_meta(value=url, limit=limit, started_at=started_at),
            )

        try:
            result = asyncio.run(_run_read(normalized))
        except ImportError:
            return self.error_result(
                "read",
                code="missing_dependency",
                message=(
                    "crawl4ai is not installed. For external project environments, "
                    f"{_EXTRA_INSTALL_HINT}; then run {_BROWSER_INSTALL_HINT}. "
                    f"For checkout development, use {_CHECKOUT_INSTALL_HINT}."
                ),
                meta=self.make_meta(value=normalized, limit=limit, started_at=started_at),
            )
        except Exception as exc:
            code, message = _classify_runtime_failure(exc)
            return self.error_result(
                "read",
                code=code,
                message=message,
                meta=self.make_meta(value=normalized, limit=limit, started_at=started_at),
            )

        item = _normalize_page_item(result, fallback_url=normalized)
        item_hygiene = item["extras"].get("extraction_hygiene")
        hygiene_meta = item_hygiene if isinstance(item_hygiene, dict) else {}
        return self.ok_result(
            "read",
            items=[item],
            raw=_raw_page(result, fallback_url=normalized),
            meta=self.make_meta(
                value=normalized,
                limit=limit,
                started_at=started_at,
                **hygiene_meta,
                extraction_hygiene=dict(hygiene_meta),
            ),
        )

    def crawl(self, url: str, limit: int = 10, crawl_query: str | None = None) -> CollectionResult:
        started_at = time.perf_counter()
        normalized = _validated_http_url(_normalize_url(url))
        if normalized is None:
            return self.error_result(
                "crawl",
                code="invalid_input",
                message="crawl4ai crawl requires an http or https URL",
                meta=self.make_meta(value=url, limit=limit, started_at=started_at),
            )

        if not crawl_query or not crawl_query.strip():
            return self.error_result(
                "crawl",
                code="invalid_input",
                message="crawl4ai crawl requires a non-empty crawl_query",
                meta=self.make_meta(value=normalized, limit=limit, started_at=started_at),
            )

        max_pages = limit or 10
        query_text = crawl_query.strip()
        try:
            results = asyncio.run(_run_crawl(normalized, query_text, max_pages))
        except ImportError:
            return self.error_result(
                "crawl",
                code="missing_dependency",
                message=(
                    "crawl4ai is not installed. For external project environments, "
                    f"{_EXTRA_INSTALL_HINT}; then run {_BROWSER_INSTALL_HINT}. "
                    f"For checkout development, use {_CHECKOUT_INSTALL_HINT}."
                ),
                meta=self.make_meta(
                    value=normalized,
                    limit=max_pages,
                    started_at=started_at,
                    crawl_query=query_text,
                ),
            )
        except Exception as exc:
            code, message = _classify_runtime_failure(exc)
            return self.error_result(
                "crawl",
                code=code,
                message=message,
                meta=self.make_meta(
                    value=normalized,
                    limit=max_pages,
                    started_at=started_at,
                    crawl_query=query_text,
                ),
            )

        kept_items: list[NormalizedItem] = []
        kept_raw_pages: list[dict] = []
        skipped_external: list[str] = []
        failed_pages: list[dict] = []
        for result in results:
            page = _raw_page(result, fallback_url=normalized)
            page_url = str(page.get("final_url") or page.get("url") or normalized)
            if not _same_origin(page_url, normalized):
                skipped_external.append(page_url)
                continue
            if not page.get("success", True):
                failed_pages.append({"url": page_url, "error_message": page.get("error_message")})
                continue
            kept_items.append(
                _normalize_page_item(result, fallback_url=normalized, crawl_query=query_text)
            )
            kept_raw_pages.append(page)

        return self.ok_result(
            "crawl",
            items=kept_items[:max_pages],
            raw={
                "start_url": normalized,
                "query": query_text,
                "pages": kept_raw_pages[:max_pages],
                "failed_pages": failed_pages,
                "skipped_external_urls": skipped_external,
            },
            meta=self.make_meta(
                value=normalized,
                limit=max_pages,
                started_at=started_at,
                crawl_query=query_text,
                returned_pages=len(results),
                kept_pages=min(len(kept_items), max_pages),
                skipped_external_count=len(skipped_external),
                failed_page_count=len(failed_pages),
            ),
        )

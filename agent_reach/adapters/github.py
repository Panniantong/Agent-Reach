# -*- coding: utf-8 -*-
"""GitHub collection adapter."""

from __future__ import annotations

import json
import time
from urllib.parse import urlparse

from agent_reach.results import (
    CollectionResult,
    NormalizedItem,
    build_item,
    build_pagination_meta,
    parse_timestamp,
)
from agent_reach.source_hints import github_source_hints

from .base import BaseAdapter

_SEARCH_PAGE_SIZE_MAX = 100


def _normalize_repository(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    if "github.com" not in text:
        return text if "/" in text else None
    parsed = urlparse(text)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 2:
        return None
    return f"{segments[0]}/{segments[1]}"


def _normalize_page_size(limit: int, page_size: int | None) -> int:
    if page_size is None:
        return min(max(limit, 1), _SEARCH_PAGE_SIZE_MAX)
    return min(max(page_size, 1), _SEARCH_PAGE_SIZE_MAX)


class GitHubAdapter(BaseAdapter):
    """Read and search GitHub repositories through gh CLI."""

    channel = "github"
    operations = ("search", "read")

    def search(
        self,
        query: str,
        limit: int = 5,
        page_size: int | None = None,
        max_pages: int | None = None,
        page: int | None = None,
    ) -> CollectionResult:
        started_at = time.perf_counter()
        gh = self.command_path("gh")
        if not gh:
            return self.error_result(
                "search",
                code="missing_dependency",
                message="gh CLI is missing. Install it with winget install --id GitHub.cli -e",
                meta=self.make_meta(
                    value=query,
                    limit=limit,
                    started_at=started_at,
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
                    **build_pagination_meta(
                        limit=limit,
                        requested_page_size=page_size,
                        requested_max_pages=max_pages,
                        requested_page=page,
                    ),
                ),
            )

        effective_page_size = _normalize_page_size(limit, page_size)
        current_page = page or 1
        pages_fetched = 0
        total_available: int | None = None
        raw: list[dict] = []
        items: list[NormalizedItem] = []
        has_more = False
        next_page: int | None = None

        while len(raw) < limit and (max_pages is None or pages_fetched < max_pages):
            remaining = limit - len(raw)
            request_page_size = min(effective_page_size, remaining)
            try:
                result = self.run_command(
                    [
                        gh,
                        "api",
                        "-X",
                        "GET",
                        "search/repositories",
                        "-f",
                        f"q={query}",
                        "-f",
                        f"per_page={request_page_size}",
                        "-f",
                        f"page={current_page}",
                    ],
                    timeout=60,
                )
            except Exception as exc:
                return self.error_result(
                    "search",
                    code="command_failed",
                    message=f"GitHub search failed: {exc}",
                    meta=self.make_meta(
                        value=query,
                        limit=limit,
                        started_at=started_at,
                        **build_pagination_meta(
                            limit=limit,
                            requested_page_size=page_size,
                            requested_max_pages=max_pages,
                            requested_page=page,
                        ),
                    ),
                )

            raw_output = f"{result.stdout}\n{result.stderr}".strip()
            if result.returncode != 0:
                return self.error_result(
                    "search",
                    code="command_failed",
                    message="GitHub search command did not complete cleanly",
                    raw=raw_output,
                    meta=self.make_meta(
                        value=query,
                        limit=limit,
                        started_at=started_at,
                        **build_pagination_meta(
                            limit=limit,
                            requested_page_size=page_size,
                            requested_max_pages=max_pages,
                            requested_page=page,
                        ),
                    ),
                    details={"returncode": result.returncode},
                )

            try:
                page_payload = json.loads(result.stdout or "{}")
            except json.JSONDecodeError:
                return self.error_result(
                    "search",
                    code="invalid_response",
                    message="GitHub search returned a non-JSON payload",
                    raw=raw_output,
                    meta=self.make_meta(
                        value=query,
                        limit=limit,
                        started_at=started_at,
                        **build_pagination_meta(
                            limit=limit,
                            requested_page_size=page_size,
                            requested_max_pages=max_pages,
                            requested_page=page,
                        ),
                    ),
                )
            if not isinstance(page_payload, dict) or not isinstance(page_payload.get("items"), list):
                return self.error_result(
                    "search",
                    code="invalid_response",
                    message="GitHub search payload did not include an items list",
                    raw=page_payload,
                    meta=self.make_meta(
                        value=query,
                        limit=limit,
                        started_at=started_at,
                        **build_pagination_meta(
                            limit=limit,
                            requested_page_size=page_size,
                            requested_max_pages=max_pages,
                            requested_page=page,
                        ),
                    ),
                )

            pages_fetched += 1
            if total_available is None:
                raw_total_available = page_payload.get("total_count")
                total_available = int(raw_total_available) if isinstance(raw_total_available, int) else None

            page_items = [repo for repo in page_payload.get("items", []) if isinstance(repo, dict)]
            raw.extend(page_items)
            for idx, repo in enumerate(page_items, start=len(items)):
                published_at = parse_timestamp(repo.get("updatedAt"))
                items.append(
                    build_item(
                        item_id=repo.get("fullName")
                        or repo.get("url")
                        or repo.get("name")
                        or f"github-{idx}",
                        kind="repository",
                        title=repo.get("fullName") or repo.get("name"),
                        url=repo.get("url"),
                        text=repo.get("description"),
                        author=(repo.get("owner") or {}).get("login"),
                        published_at=published_at,
                        source=self.channel,
                        extras={
                            "stars": repo.get("stargazersCount"),
                            "language": repo.get("language"),
                            "source_hints": github_source_hints(published_at),
                        },
                    )
                )

            absolute_consumed = ((current_page - 1) * effective_page_size) + len(page_items)
            has_more = False
            if total_available is not None:
                has_more = absolute_consumed < total_available
            elif page_items and len(page_items) == request_page_size:
                has_more = True
            next_page = current_page + 1 if has_more else None
            if not has_more or len(items) >= limit:
                break
            current_page += 1

        return self.ok_result(
            "search",
            items=items,
            raw=raw,
            meta=self.make_meta(
                value=query,
                limit=limit,
                started_at=started_at,
                backend="gh_api",
                **build_pagination_meta(
                    limit=limit,
                    requested_page_size=page_size,
                    requested_max_pages=max_pages,
                    requested_page=page,
                    page_size=effective_page_size,
                    pages_fetched=pages_fetched,
                    next_page=next_page,
                    has_more=has_more,
                    total_available=total_available,
                ),
            ),
        )

    def read(self, repository: str, limit: int | None = None) -> CollectionResult:
        started_at = time.perf_counter()
        gh = self.command_path("gh")
        if not gh:
            return self.error_result(
                "read",
                code="missing_dependency",
                message="gh CLI is missing. Install it with winget install --id GitHub.cli -e",
                meta=self.make_meta(value=repository, limit=limit, started_at=started_at),
            )

        repo_name = _normalize_repository(repository)
        if not repo_name:
            return self.error_result(
                "read",
                code="invalid_input",
                message="GitHub read expects owner/repo or a github.com repository URL",
                meta=self.make_meta(value=repository, limit=limit, started_at=started_at),
            )

        try:
            result = self.run_command(
                [
                    gh,
                    "repo",
                    "view",
                    repo_name,
                    "--json",
                    "name,nameWithOwner,description,url,owner,homepageUrl,stargazerCount,forkCount,updatedAt,createdAt,licenseInfo,primaryLanguage,isPrivate,isArchived,defaultBranchRef,repositoryTopics",
                ],
                timeout=60,
            )
        except Exception as exc:
            return self.error_result(
                "read",
                code="command_failed",
                message=f"GitHub read failed: {exc}",
                meta=self.make_meta(value=repo_name, limit=limit, started_at=started_at),
            )

        raw_output = f"{result.stdout}\n{result.stderr}".strip()
        if result.returncode != 0:
            return self.error_result(
                "read",
                code="command_failed",
                message="GitHub repo view did not complete cleanly",
                raw=raw_output,
                meta=self.make_meta(value=repo_name, limit=limit, started_at=started_at),
                details={"returncode": result.returncode},
            )

        try:
            raw = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return self.error_result(
                "read",
                code="invalid_response",
                message="GitHub repo view returned a non-JSON payload",
                raw=raw_output,
                meta=self.make_meta(value=repo_name, limit=limit, started_at=started_at),
            )
        published_at = parse_timestamp(raw.get("updatedAt"))
        item = build_item(
            item_id=raw.get("nameWithOwner") or repo_name,
            kind="repository",
            title=raw.get("nameWithOwner") or raw.get("name") or repo_name,
            url=raw.get("url"),
            text=raw.get("description"),
            author=(raw.get("owner") or {}).get("login"),
            published_at=published_at,
            source=self.channel,
            extras={
                "homepage_url": raw.get("homepageUrl"),
                "stars": raw.get("stargazerCount"),
                "forks": raw.get("forkCount"),
                "created_at": parse_timestamp(raw.get("createdAt")),
                "license": (raw.get("licenseInfo") or {}).get("name"),
                "primary_language": (raw.get("primaryLanguage") or {}).get("name"),
                "is_private": raw.get("isPrivate"),
                "is_archived": raw.get("isArchived"),
                "default_branch": (raw.get("defaultBranchRef") or {}).get("name"),
                "topics": [topic.get("name") for topic in raw.get("repositoryTopics") or [] if topic.get("name")],
                "source_hints": github_source_hints(published_at),
            },
        )
        return self.ok_result(
            "read",
            items=[item],
            raw=raw,
            meta=self.make_meta(value=repo_name, limit=limit, started_at=started_at),
        )

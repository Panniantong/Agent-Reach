# -*- coding: utf-8 -*-
"""MCP Registry collection adapter."""

from __future__ import annotations

import time
import warnings
from urllib.parse import quote, unquote, urlparse

from agent_reach.results import (
    CollectionResult,
    NormalizedItem,
    build_item,
    build_pagination_meta,
    parse_timestamp,
)
from agent_reach.source_hints import registry_entry_source_hints

from .base import BaseAdapter

_UA = "agent-reach/1.6.0 (+https://github.com/iwachacha/Agent-Reach)"
_BASE_URL = "https://registry.modelcontextprotocol.io"
_PAGE_SIZE = 100
_MAX_PAGES = 5


def _import_requests():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"urllib3 .* doesn't match a supported version!",
        )
        import requests

    return requests


def _official_meta(entry: dict) -> dict:
    raw_meta = entry.get("_meta") if isinstance(entry, dict) else {}
    meta = raw_meta if isinstance(raw_meta, dict) else {}
    official = meta.get("io.modelcontextprotocol.registry/official")
    return official if isinstance(official, dict) else {}


def _server(entry: dict) -> dict:
    raw_server = entry.get("server") if isinstance(entry, dict) else {}
    return raw_server if isinstance(raw_server, dict) else {}


def _remote_urls(server: dict) -> list[str]:
    urls: list[str] = []
    for remote in server.get("remotes") or []:
        if isinstance(remote, dict) and remote.get("url"):
            urls.append(str(remote["url"]))
    return urls


def _published_at(entry: dict) -> str | None:
    official = _official_meta(entry)
    return parse_timestamp(
        official.get("publishedAt")
        or official.get("published_at")
        or official.get("createdAt")
        or official.get("updatedAt")
    )


def _registry_url(name: str, version: str | None = None) -> str:
    version_text = version or "latest"
    return f"{_BASE_URL}/v0.1/servers/{quote(name, safe='')}/versions/{quote(version_text, safe='')}"


def _entry_item(entry: dict, idx: int, *, source: str) -> NormalizedItem:
    server = _server(entry)
    official = _official_meta(entry)
    name = str(server.get("name") or f"mcp-server-{idx}")
    published_at = _published_at(entry)
    raw_repository = server.get("repository")
    repository = raw_repository if isinstance(raw_repository, dict) else {}
    remotes = _remote_urls(server)
    return build_item(
        item_id=name,
        kind="mcp_server",
        title=name,
        url=repository.get("url") or server.get("websiteUrl") or server.get("website_url") or (remotes[0] if remotes else None),
        text=server.get("description"),
        author=None,
        published_at=published_at,
        source=source,
        extras={
            "version": server.get("version"),
            "registry_url": _registry_url(name, str(server.get("version") or "latest")),
            "repository_url": repository.get("url"),
            "repository_source": repository.get("source"),
            "website_url": server.get("websiteUrl") or server.get("website_url"),
            "remotes": server.get("remotes") or [],
            "registry_status": official.get("status"),
            "registry_updated_at": parse_timestamp(official.get("updatedAt") or official.get("updated_at")),
            "registry_status_changed_at": parse_timestamp(
                official.get("statusChangedAt") or official.get("status_changed_at")
            ),
            "is_latest": official.get("isLatest"),
            "source_hints": registry_entry_source_hints(published_at),
        },
    )


def _search_text(entry: dict) -> str:
    server = _server(entry)
    raw_repository = server.get("repository")
    repository = raw_repository if isinstance(raw_repository, dict) else {}
    parts = [
        server.get("name"),
        server.get("description"),
        repository.get("url"),
        server.get("websiteUrl") or server.get("website_url"),
        *_remote_urls(server),
    ]
    return " ".join(str(part).lower() for part in parts if part)


def _matches_query(entry: dict, query: str) -> bool:
    tokens = [token.lower() for token in query.split() if token.strip()]
    if not tokens:
        return True
    haystack = _search_text(entry)
    return all(token in haystack for token in tokens)


def _parse_read_input(value: str) -> tuple[str, str]:
    text = value.strip()
    parsed = urlparse(text)
    if parsed.netloc:
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if "servers" in parts:
            idx = parts.index("servers")
            if idx + 1 < len(parts):
                name = parts[idx + 1]
                version = "latest"
                if idx + 3 < len(parts) and parts[idx + 2] == "versions":
                    version = parts[idx + 3]
                return name, version
    if "@version=" in text:
        name, version = text.split("@version=", 1)
        return name.strip(), version.strip() or "latest"
    if " versions/" in text:
        name, version = text.split(" versions/", 1)
        return name.strip(), version.strip() or "latest"
    return text, "latest"


class MCPRegistryAdapter(BaseAdapter):
    """Search and read the public MCP Registry."""

    channel = "mcp_registry"
    operations = ("search", "read")

    def search(self, query: str, limit: int = 10) -> CollectionResult:
        started_at = time.perf_counter()
        requests = _import_requests()
        entries: list[dict] = []
        raw_pages: list[dict] = []
        cursor = None
        pages_fetched = 0

        while pages_fetched < _MAX_PAGES and len(entries) < limit:
            params = {"limit": _PAGE_SIZE}
            if cursor:
                params["cursor"] = cursor
            try:
                response = requests.get(
                    f"{_BASE_URL}/v0.1/servers",
                    params=params,
                    headers={"User-Agent": _UA, "Accept": "application/json"},
                    timeout=30,
                )
            except requests.RequestException as exc:
                return self.error_result(
                    "search",
                    code="http_error",
                    message=f"MCP Registry search failed: {exc}",
                    meta=self.make_meta(value=query, limit=limit, started_at=started_at),
                )

            if response.status_code >= 400:
                return self.error_result(
                    "search",
                    code="http_error",
                    message=f"MCP Registry search returned HTTP {response.status_code}",
                    raw=response.text,
                    meta=self.make_meta(value=query, limit=limit, started_at=started_at),
                )
            try:
                page = response.json()
            except ValueError:
                return self.error_result(
                    "search",
                    code="invalid_response",
                    message="MCP Registry search returned a non-JSON payload",
                    raw=response.text,
                    meta=self.make_meta(value=query, limit=limit, started_at=started_at),
                )
            if not isinstance(page, dict) or not isinstance(page.get("servers"), list):
                return self.error_result(
                    "search",
                    code="invalid_response",
                    message="MCP Registry search payload did not include a servers list",
                    raw=page,
                    meta=self.make_meta(value=query, limit=limit, started_at=started_at),
                )

            raw_pages.append(page)
            pages_fetched += 1
            for entry in page["servers"]:
                if isinstance(entry, dict) and _matches_query(entry, query):
                    entries.append(entry)
                    if len(entries) >= limit:
                        break
            raw_metadata = page.get("metadata")
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            cursor = metadata.get("nextCursor") or metadata.get("next_cursor")
            if not cursor:
                break

        items = [_entry_item(entry, idx, source=self.channel) for idx, entry in enumerate(entries[:limit])]
        return self.ok_result(
            "search",
            items=items,
            raw={"pages": raw_pages},
            meta=self.make_meta(
                value=query,
                limit=limit,
                started_at=started_at,
                base_url=_BASE_URL,
                pages_scanned=pages_fetched,
                scan_limit_pages=_MAX_PAGES,
                **build_pagination_meta(
                    limit=limit,
                    page_size=_PAGE_SIZE,
                    pages_fetched=pages_fetched,
                    next_cursor=cursor,
                    has_more=bool(cursor),
                ),
            ),
        )

    def read(self, server_name_or_url: str, limit: int | None = None) -> CollectionResult:
        started_at = time.perf_counter()
        server_name, version = _parse_read_input(server_name_or_url)
        if not server_name:
            return self.error_result(
                "read",
                code="invalid_input",
                message="MCP Registry read input must be a server name or registry server URL",
                meta=self.make_meta(value=server_name_or_url, limit=limit, started_at=started_at),
            )
        requests = _import_requests()
        try:
            response = requests.get(
                _registry_url(server_name, version),
                headers={"User-Agent": _UA, "Accept": "application/json"},
                timeout=30,
            )
        except requests.RequestException as exc:
            return self.error_result(
                "read",
                code="http_error",
                message=f"MCP Registry read failed: {exc}",
                meta=self.make_meta(value=server_name, limit=limit, started_at=started_at, version=version),
            )

        if response.status_code == 404:
            return self.error_result(
                "read",
                code="not_found",
                message=f"MCP Registry server not found: {server_name}@{version}",
                raw=response.text,
                meta=self.make_meta(value=server_name, limit=limit, started_at=started_at, version=version),
            )
        if response.status_code >= 400:
            return self.error_result(
                "read",
                code="http_error",
                message=f"MCP Registry read returned HTTP {response.status_code}",
                raw=response.text,
                meta=self.make_meta(value=server_name, limit=limit, started_at=started_at, version=version),
            )
        try:
            raw = response.json()
        except ValueError:
            return self.error_result(
                "read",
                code="invalid_response",
                message="MCP Registry read returned a non-JSON payload",
                raw=response.text,
                meta=self.make_meta(value=server_name, limit=limit, started_at=started_at, version=version),
            )
        if not isinstance(raw, dict) or not isinstance(raw.get("server"), dict):
            return self.error_result(
                "read",
                code="invalid_response",
                message="MCP Registry read payload did not include a server object",
                raw=raw,
                meta=self.make_meta(value=server_name, limit=limit, started_at=started_at, version=version),
            )
        item = _entry_item(raw, 0, source=self.channel)
        return self.ok_result(
            "read",
            items=[item],
            raw=raw,
            meta=self.make_meta(
                value=server_name,
                limit=limit,
                started_at=started_at,
                version=version,
                base_url=_BASE_URL,
                **build_pagination_meta(limit=limit, page_size=1, pages_fetched=1, has_more=False),
            ),
        )

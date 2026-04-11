# -*- coding: utf-8 -*-
"""Public SDK for external Agent Reach consumers."""

from __future__ import annotations

from typing import Dict, Optional

from agent_reach.adapters import get_adapter
from agent_reach.channels import get_all_channel_contracts
from agent_reach.config import Config
from agent_reach.operation_contracts import OperationContractError, validate_operation_options
from agent_reach.results import CollectionResult, build_error, build_result


class _Namespace:
    """Thin per-channel SDK namespace."""

    def __init__(self, client: "AgentReachClient", channel: str):
        self._client = client
        self._channel = channel

    def read(self, value: str, limit: int | None = None) -> CollectionResult:
        """Run the standard read operation for this channel."""

        return self._client.collect(self._channel, "read", value, limit=limit)

    def search(self, value: str, limit: int | None = None) -> CollectionResult:
        """Run the standard search operation for this channel."""

        return self._client.collect(self._channel, "search", value, limit=limit)

    def user(self, value: str, limit: int | None = None) -> CollectionResult:
        """Run a profile lookup operation when supported by this channel."""

        return self._client.collect(self._channel, "user", value, limit=limit)

    def user_posts(self, value: str, limit: int | None = None) -> CollectionResult:
        """Run a user posts lookup operation when supported by this channel."""

        return self._client.collect(self._channel, "user_posts", value, limit=limit)

    def tweet(self, value: str, limit: int | None = None) -> CollectionResult:
        """Run a single tweet/thread lookup operation when supported by this channel."""

        return self._client.collect(self._channel, "tweet", value, limit=limit)

    def crawl(
        self,
        value: str,
        limit: int | None = None,
        *,
        query: str | None = None,
    ) -> CollectionResult:
        """Run a bounded crawl operation when supported by this channel."""

        return self._client.collect(self._channel, "crawl", value, limit=limit, crawl_query=query)

    def top(self, value: str = "top", limit: int | None = None) -> CollectionResult:
        """Run a top-list operation when supported by this channel."""

        return self._client.collect(self._channel, "top", value, limit=limit)

    def new(self, value: str = "new", limit: int | None = None) -> CollectionResult:
        """Run a new-list operation when supported by this channel."""

        return self._client.collect(self._channel, "new", value, limit=limit)

    def best(self, value: str = "best", limit: int | None = None) -> CollectionResult:
        """Run a best-list operation when supported by this channel."""

        return self._client.collect(self._channel, "best", value, limit=limit)


class AgentReachClient:
    """Public SDK for diagnostics, registry lookups, and read-only collection."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.web = _Namespace(self, "web")
        self.exa = _Namespace(self, "exa_search")
        self.exa_search = self.exa
        self.github = _Namespace(self, "github")
        self.hatena_bookmark = _Namespace(self, "hatena_bookmark")
        self.hatena = self.hatena_bookmark
        self.bluesky = _Namespace(self, "bluesky")
        self.qiita = _Namespace(self, "qiita")
        self.youtube = _Namespace(self, "youtube")
        self.rss = _Namespace(self, "rss")
        self.searxng = _Namespace(self, "searxng")
        self.crawl4ai = _Namespace(self, "crawl4ai")
        self.hacker_news = _Namespace(self, "hacker_news")
        self.hn = self.hacker_news
        self.mcp_registry = _Namespace(self, "mcp_registry")
        self.reddit = _Namespace(self, "reddit")
        self.twitter = _Namespace(self, "twitter")

    def doctor(self) -> Dict[str, dict]:
        from agent_reach.doctor import check_all

        return check_all(self.config)

    def doctor_payload(self, probe: bool = False) -> dict:
        from agent_reach.doctor import check_all, make_doctor_payload

        return make_doctor_payload(check_all(self.config, probe=probe), probe=probe)

    def doctor_report(self) -> str:
        from agent_reach.doctor import check_all, format_report

        return format_report(check_all(self.config))

    def channels(self) -> list[dict]:
        """Return the stable channel registry contract."""

        return get_all_channel_contracts()

    def collect(
        self,
        channel: str,
        operation: str,
        value: str,
        limit: int | None = None,
        body_mode: str | None = None,
        crawl_query: str | None = None,
        page_size: int | None = None,
        max_pages: int | None = None,
        cursor: str | None = None,
        page: int | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> CollectionResult:
        """Run a supported collection operation and return a stable result envelope."""

        text_value = value.strip()
        if not text_value:
            return build_result(
                ok=False,
                channel=channel,
                operation=operation,
                meta={"input": value},
                error=build_error(
                    code="invalid_input",
                    message="Collection input must not be empty",
                    details={},
                ),
            )

        if limit is not None and limit < 1:
            return build_result(
                ok=False,
                channel=channel,
                operation=operation,
                meta={"input": text_value, "limit": limit},
                error=build_error(
                    code="invalid_input",
                    message="limit must be greater than or equal to 1",
                    details={"limit": limit},
                ),
            )

        options = {
            "body_mode": body_mode,
            "crawl_query": crawl_query,
            "page_size": page_size,
            "max_pages": max_pages,
            "cursor": cursor,
            "page": page,
            "since": since,
            "until": until,
        }
        adapter = get_adapter(channel, config=self.config)
        if adapter is None:
            return build_result(
                ok=False,
                channel=channel,
                operation=operation,
                meta={"input": text_value},
                error=build_error(
                    code="unknown_channel",
                    message=f"Unknown channel: {channel}",
                    details={},
                ),
            )

        if operation not in adapter.supported_operations():
            return build_result(
                ok=False,
                channel=channel,
                operation=operation,
                meta={
                    "input": text_value,
                    "supported_operations": list(adapter.supported_operations()),
                },
                error=build_error(
                    code="unsupported_operation",
                    message=f"{channel} does not support operation: {operation}",
                    details={"supported_operations": list(adapter.supported_operations())},
                ),
            )

        try:
            validate_operation_options(
                channel,
                operation,
                options,
            )
        except OperationContractError as exc:
            return build_result(
                ok=False,
                channel=channel,
                operation=operation,
                meta={
                    "input": text_value,
                    **({"limit": limit} if limit is not None else {}),
                    **({key: value for key, value in options.items() if value is not None}),
                },
                error=build_error(code=exc.code, message=exc.message, details=exc.details),
            )

        normalized_options = dict(options)
        for option_name in ("page_size", "max_pages", "page"):
            raw_option = normalized_options.get(option_name)
            if raw_option is not None:
                normalized_options[option_name] = int(raw_option)

        method = getattr(adapter, operation)
        try:
            call_kwargs: dict[str, object] = {}
            if limit is not None:
                call_kwargs["limit"] = limit
            for option_name, option_value in normalized_options.items():
                if option_value is not None:
                    call_kwargs[option_name] = option_value
            return method(text_value, **call_kwargs)
        except Exception as exc:
            return build_result(
                ok=False,
                channel=channel,
                operation=operation,
                meta={"input": text_value, **({"limit": limit} if limit is not None else {})},
                error=build_error(
                    code="internal_error",
                    message=f"{channel} {operation} raised an unexpected error: {exc}",
                    details={"exception_type": type(exc).__name__},
                ),
            )


class AgentReach(AgentReachClient):
    """Backward-compatible facade for existing health-check consumers."""

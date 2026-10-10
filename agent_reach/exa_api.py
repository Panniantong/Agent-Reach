# -*- coding: utf-8 -*-
"""Direct Exa REST commands with the same defaults as Exa MCP."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Mapping

import requests

from agent_reach import __version__
from agent_reach.config import Config, ConfigError

EXA_API_BASE = "https://api.exa.ai"
_CATEGORY_RE = re.compile(
    r"\bcategory:(company|publication|news|personal\s*site|people)\b",
    re.IGNORECASE,
)
_TRANSIENT_STATUS_CODES = {500, 502, 503, 504}
_DEFAULT_NUM_RESULTS = 10
_DEFAULT_MAX_CHARACTERS = 3000
_REQUEST_TIMEOUT_SECONDS = 60.0


class ExaClientError(RuntimeError):
    """A user-safe Exa client failure with a stable process exit code."""

    def __init__(self, message: str, exit_code: int = 7):
        super().__init__(message)
        self.exit_code = exit_code


def require_api_key(config: Mapping[str, Any] | Config | None = None) -> str:
    """Load an Exa key from Agent Reach config or ``EXA_API_KEY``."""
    if config is None:
        value = os.environ.get("EXA_API_KEY")
        if not value:
            try:
                value = Config(read_only=True).get("exa_api_key")
            except (ConfigError, OSError, UnicodeError):
                raise ExaClientError("Agent Reach config could not be read safely", 3) from None
    else:
        value = config.get("exa_api_key")
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\n" in value
        or "\r" in value
    ):
        raise ExaClientError(
            "EXA_API_KEY is not configured; run `agent-reach configure exa-key`",
            3,
        )
    return value


def build_search_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Mirror ``web_search_exa`` request defaults over REST."""
    query = args.query.strip()
    if not query:
        raise ExaClientError("query must not be empty", 2)

    num_results = _DEFAULT_NUM_RESULTS if args.num_results is None else args.num_results
    if not 1 <= num_results <= 100:
        raise ExaClientError("num-results must be between 1 and 100", 2)

    category_match = _CATEGORY_RE.search(query)
    category = None
    if category_match:
        category = re.sub(r"\s+", " ", category_match.group(1).lower())
        query = query[: category_match.start()] + query[category_match.end() :]
        query = re.sub(r"\s+", " ", query).strip()
        if not query:
            raise ExaClientError("query must not be empty after category extraction", 2)

    payload: dict[str, Any] = {
        "query": query,
        "type": "auto",
        "numResults": num_results,
        "contents": {"highlights": True},
    }
    if category:
        payload["category"] = category
    return payload


def build_contents_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Mirror ``web_fetch_exa`` request defaults over REST."""
    if not args.urls:
        raise ExaClientError("contents requires at least one URL", 2)
    if args.max_characters <= 0:
        raise ExaClientError("max-characters must be greater than zero", 2)
    return {
        "urls": list(args.urls),
        "text": {"maxCharacters": args.max_characters},
    }


def request_json(
    endpoint: str,
    payload: dict[str, Any],
    *,
    api_key: str,
    timeout: float = _REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """POST JSON to Exa without exposing the API key in URLs or errors."""
    deadline = time.monotonic() + timeout
    response = None
    for attempt in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ExaClientError(f"request timed out after {timeout:g}s", 7)
        try:
            response = requests.post(
                f"{EXA_API_BASE}/{endpoint}",
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": f"agent-reach/{__version__}",
                    "x-api-key": api_key,
                    "x-exa-integration": "agent-reach-rest",
                },
                json=payload,
                timeout=remaining,
            )
        except requests.RequestException as exc:
            raise ExaClientError(
                f"transport failure: {type(exc).__name__}",
                7,
            ) from None

        if response.status_code not in _TRANSIENT_STATUS_CODES or attempt == 2:
            break

        delay = 2**attempt
        if time.monotonic() + delay >= deadline:
            raise ExaClientError(f"request timed out after {timeout:g}s", 7)
        time.sleep(delay)

    assert response is not None
    try:
        body = response.json()
    except ValueError:
        body = None

    if response.status_code == 401:
        raise ExaClientError("HTTP 401: API key rejected", 4)
    if response.status_code == 402:
        raise ExaClientError("HTTP 402: credits exhausted or key budget exceeded", 5)
    if response.status_code == 429:
        raise ExaClientError("HTTP 429: Exa rate limit reached", 6)
    if not response.ok:
        raise ExaClientError(f"HTTP {response.status_code}: Exa request failed", 7)
    if not isinstance(body, dict):
        raise ExaClientError("Exa returned a non-object JSON response", 7)
    return body


def format_search_response(body: dict[str, Any]) -> str:
    """Match ``web_search_exa`` human-readable output."""
    results = body.get("results")
    if not isinstance(results, list) or not results:
        return "No search results found. Please try a different query."

    blocks = []
    for result in results:
        if not isinstance(result, dict):
            continue
        lines = [
            f"Title: {result.get('title') or 'N/A'}",
            f"URL: {result.get('url') or 'N/A'}",
            f"Published: {result.get('publishedDate') or 'N/A'}",
            f"Author: {result.get('author') or 'N/A'}",
        ]
        highlights = result.get("highlights")
        clean_highlights = []
        if isinstance(highlights, list):
            clean_highlights = [item for item in highlights if isinstance(item, str)]
        if clean_highlights:
            lines.append("Highlights:\n" + "\n".join(clean_highlights))
        elif isinstance(result.get("text"), str):
            lines.append(f"Text: {result['text']}")
        blocks.append("\n".join(lines))
    return "\n\n---\n\n".join(blocks)


def format_contents_response(body: dict[str, Any]) -> tuple[str, bool]:
    """Match ``web_fetch_exa`` clean-Markdown output and error state."""
    results = body.get("results")
    clean_results = results if isinstance(results, list) else []
    statuses = body.get("statuses")
    errors: list[tuple[str, str]] = []
    if isinstance(statuses, list):
        for status in statuses:
            if not isinstance(status, dict) or status.get("status") != "error":
                continue
            raw_error = status.get("error")
            error = raw_error if isinstance(raw_error, dict) else {}
            errors.append(
                (
                    str(status.get("id") or "unknown URL"),
                    str(error.get("tag") or "unknown error"),
                )
            )

    if not clean_results:
        if errors:
            detail = "; ".join(f"{url}: {tag}" for url, tag in errors)
            return f"Error fetching URL(s): {detail}", True
        return "No content found for the provided URL(s).", False

    lines: list[str] = []
    for result in clean_results:
        if not isinstance(result, dict):
            continue
        lines.append(f"# {result.get('title') or '(no title)'}")
        lines.append(f"URL: {result.get('url') or 'N/A'}")
        if isinstance(result.get("publishedDate"), str):
            lines.append(f"Published: {result['publishedDate'].split('T')[0]}")
        if isinstance(result.get("author"), str) and result["author"]:
            lines.append(f"Author: {result['author']}")
        lines.append("")
        if isinstance(result.get("text"), str) and result["text"]:
            lines.append(result["text"])
        lines.append("")
    for url, tag in errors:
        lines.append(f"Error fetching {url}: {tag}")
    return "\n".join(lines).strip() or "No content found.", False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-reach-exa",
        description="Call Exa REST directly with Agent Reach routing defaults",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Check local credential readiness")
    status.add_argument("--json", action="store_true", help="Emit machine-readable status")

    search = sub.add_parser("search", help="Search Exa without MCP")
    search.add_argument("query", help="Natural-language search query")
    search.add_argument(
        "--num-results",
        type=int,
        default=None,
        help="Number of results; omitted preserves Exa MCP's default of 10",
    )

    contents = sub.add_parser("contents", help="Fetch selected URLs")
    contents.add_argument("urls", nargs="+")
    contents.add_argument("--max-characters", type=int, default=_DEFAULT_MAX_CHARACTERS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        api_key = require_api_key()
        if args.command == "status":
            result = {
                "configured": True,
                "backend": "Exa REST API",
                "live_probe": False,
            }
            print(
                json.dumps(result, ensure_ascii=False)
                if args.json
                else "Exa REST credential configured (not live-probed)"
            )
            return 0

        if args.command == "search":
            payload = build_search_payload(args)
            body = request_json("search", payload, api_key=api_key)
            rendered = format_search_response(body)
            is_error = False
        else:
            payload = build_contents_payload(args)
            body = request_json("contents", payload, api_key=api_key)
            rendered, is_error = format_contents_response(body)

        print(rendered, file=sys.stderr if is_error else sys.stdout)
        return 7 if is_error else 0
    except ExaClientError as exc:
        print(f"agent-reach-exa: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

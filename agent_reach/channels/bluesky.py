# -*- coding: utf-8 -*-
"""Bluesky channel checks."""

from __future__ import annotations

import warnings

from .base import Channel


class BlueskyChannel(Channel):
    name = "bluesky"
    description = "Bluesky public post search"
    backends = ["Bluesky AppView API"]
    tier = 0
    auth_kind = "none"
    entrypoint_kind = "python"
    operations = ["search"]
    operation_inputs = {"search": "query"}
    operation_options = {
        "search": [
            {
                "name": "page_size",
                "type": "integer",
                "required": False,
                "minimum": 1,
                "cli_flag": "--page-size",
                "sdk_kwarg": "page_size",
                "description": "Maximum Bluesky posts requested per API page.",
            },
            {
                "name": "max_pages",
                "type": "integer",
                "required": False,
                "minimum": 1,
                "cli_flag": "--max-pages",
                "sdk_kwarg": "max_pages",
                "description": "Maximum Bluesky API pages to request before stopping with pagination metadata.",
            },
            {
                "name": "cursor",
                "type": "string",
                "required": False,
                "cli_flag": "--cursor",
                "sdk_kwarg": "cursor",
                "description": "Starting Bluesky continuation cursor.",
            },
        ]
    }
    host_patterns = [
        "https://bsky.app/*",
        "https://public.api.bsky.app/*",
        "https://api.bsky.app/*",
    ]
    example_invocations = [
        'agent-reach collect --channel bluesky --operation search --input "OpenAI" --limit 10 --json',
    ]
    supports_probe = True
    install_hints = [
        "Uses the public Bluesky AppView endpoints over HTTPS.",
    ]

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        host = urlparse(url).netloc.lower()
        return "bsky.app" in host or "bsky.social" in host

    def check(self, config=None):
        if not _has_requests():
            return "off", "requests is missing. Install it with pip install requests"
        return "ok", "Ready for public Bluesky post search"

    def probe(self, config=None):
        from agent_reach.adapters.bluesky import BlueskyAdapter

        payload = BlueskyAdapter(config=config).search("OpenAI", limit=1)
        if payload["ok"]:
            return "ok", "Bluesky AppView completed a live probe search"
        return "warn", payload["error"]["message"] if payload["error"] else "Bluesky probe failed"


def _has_requests() -> bool:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"urllib3 .* doesn't match a supported version!",
        )
        try:
            import requests  # noqa: F401
        except ImportError:
            return False
    return True

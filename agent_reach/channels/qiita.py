# -*- coding: utf-8 -*-
"""Qiita channel checks."""

from __future__ import annotations

import warnings

from .base import Channel


class QiitaChannel(Channel):
    name = "qiita"
    description = "Qiita public article search"
    backends = ["Qiita API v2"]
    tier = 0
    auth_kind = "none"
    entrypoint_kind = "python"
    operations = ["search"]
    operation_inputs = {"search": "query"}
    operation_options = {
        "search": [
            {
                "name": "body_mode",
                "type": "string",
                "required": False,
                "default": "full",
                "choices": ["none", "snippet", "full"],
                "cli_flag": "--body-mode",
                "sdk_kwarg": "body_mode",
                "description": "Control how much Qiita article body text is retained in items and raw payloads.",
            },
            {
                "name": "page_size",
                "type": "integer",
                "required": False,
                "minimum": 1,
                "cli_flag": "--page-size",
                "sdk_kwarg": "page_size",
                "description": "Maximum Qiita API items requested per page.",
            },
            {
                "name": "max_pages",
                "type": "integer",
                "required": False,
                "minimum": 1,
                "cli_flag": "--max-pages",
                "sdk_kwarg": "max_pages",
                "description": "Maximum Qiita API pages to request before stopping with pagination metadata.",
            },
            {
                "name": "page",
                "type": "integer",
                "required": False,
                "minimum": 1,
                "cli_flag": "--page",
                "sdk_kwarg": "page",
                "description": "Starting Qiita API page number.",
            },
        ]
    }
    host_patterns = ["https://qiita.com/*", "https://qiita.com/api/v2/*"]
    example_invocations = [
        'agent-reach collect --channel qiita --operation search --input "python user:Qiita" --limit 10 --json',
    ]
    supports_probe = True
    install_hints = [
        "Uses Qiita API v2 over HTTPS. Optional auth can be supplied via QIITA_TOKEN.",
    ]

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        return "qiita.com" in urlparse(url).netloc.lower()

    def check(self, config=None):
        if not _has_requests():
            return "off", "requests is missing. Install it with pip install requests"
        return "ok", "Ready for Qiita API v2 article search"

    def probe(self, config=None):
        from agent_reach.adapters.qiita import QiitaAdapter

        payload = QiitaAdapter(config=config).search("python", limit=1)
        if payload["ok"]:
            return "ok", "Qiita API completed a live probe search"
        return "warn", payload["error"]["message"] if payload["error"] else "Qiita probe failed"


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

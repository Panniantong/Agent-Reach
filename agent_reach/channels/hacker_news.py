# -*- coding: utf-8 -*-
"""Hacker News channel checks."""

from __future__ import annotations

from agent_reach.adapters.hacker_news import HackerNewsAdapter

from .base import Channel


class HackerNewsChannel(Channel):
    name = "hacker_news"
    description = "Hacker News stories, discussions, and search"
    backends = ["Hacker News API", "HN Algolia search"]
    tier = 2
    auth_kind = "none"
    entrypoint_kind = "python"
    operations = ["search", "read", "top", "new", "best", "ask", "show", "job"]
    operation_inputs = {
        "search": "query",
        "read": "post",
        "top": "list",
        "new": "list",
        "best": "list",
        "ask": "list",
        "show": "list",
        "job": "list",
    }
    host_patterns = ["https://news.ycombinator.com/*", "https://hn.algolia.com/*"]
    example_invocations = [
        'agent-reach collect --channel hacker_news --operation search --input "agent frameworks" --limit 10 --json',
        'agent-reach collect --channel hacker_news --operation top --input "top" --limit 10 --json',
        'agent-reach collect --channel hacker_news --operation read --input "https://news.ycombinator.com/item?id=8863" --json',
    ]
    supports_probe = True
    install_hints = [
        "No local install is required. Hacker News reads use public JSON APIs.",
    ]

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        host = urlparse(url).netloc.lower()
        return "news.ycombinator.com" in host or "hn.algolia.com" in host

    def check(self, config=None):
        return "ok", "Public Hacker News JSON APIs are available without local configuration"

    def probe(self, config=None):
        payload = HackerNewsAdapter(config=config).top("top", limit=1)
        if payload["ok"] and payload.get("items"):
            return "ok", "Hacker News live top-story probe succeeded"
        if payload["ok"]:
            return "warn", "Hacker News live probe completed but returned zero items"
        error = payload.get("error")
        return "warn", str((error.get("message") if error else None) or "Hacker News live probe failed")

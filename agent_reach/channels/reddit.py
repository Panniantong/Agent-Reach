# -*- coding: utf-8 -*-
"""Reddit channel checks."""

from __future__ import annotations

from agent_reach.adapters.reddit import RedditAdapter

from .base import Channel


class RedditChannel(Channel):
    name = "reddit"
    description = "Reddit search results and public discussion threads"
    backends = ["Reddit Data API"]
    tier = 2
    auth_kind = "token"
    entrypoint_kind = "python"
    operations = ["search", "read"]
    operation_inputs = {
        "search": "query",
        "read": "post",
    }
    host_patterns = ["https://www.reddit.com/*", "https://old.reddit.com/*", "https://redd.it/*"]
    example_invocations = [
        'agent-reach configure reddit-user-agent "windows:agent-reach:v1.6.0 (by /u/<username>)"',
        "agent-reach configure reddit-client-id <CLIENT_ID>",
        "agent-reach configure reddit-client-secret <CLIENT_SECRET>",
        'agent-reach collect --channel reddit --operation search --input "r/LocalLLaMA agent frameworks" --limit 10 --json',
        'agent-reach collect --channel reddit --operation read --input "https://www.reddit.com/r/redditdev/comments/..." --limit 20 --json',
    ]
    supports_probe = True
    install_hints = [
        "Create a Reddit app/client for free API access, then configure reddit-client-id and reddit-client-secret.",
        'Configure a truthful User-Agent with agent-reach configure reddit-user-agent "platform:app-id:version (by /u/username)".',
        "Alternatively provide an existing bearer token with agent-reach configure reddit-access-token <TOKEN>.",
    ]

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        host = urlparse(url).netloc.lower()
        return "reddit.com" in host or "redd.it" in host

    def check(self, config=None):
        if not config:
            return "warn", "Reddit OAuth configuration was not provided"
        user_agent = config.get("reddit_user_agent")
        access_token = config.get("reddit_access_token")
        client_id = config.get("reddit_client_id")
        client_secret = config.get("reddit_client_secret")
        if not user_agent:
            return "off", "Reddit requires a unique User-Agent. Run agent-reach configure reddit-user-agent <VALUE>"
        if access_token:
            return "ok", "Reddit bearer token and User-Agent are configured"
        if client_id and client_secret:
            return "ok", "Reddit OAuth client credentials and User-Agent are configured"
        return (
            "off",
            "Reddit OAuth is not configured. Set reddit-access-token or reddit-client-id and reddit-client-secret",
        )

    def probe(self, config=None):
        status, message = self.check(config)
        if status != "ok":
            return status, message

        payload = RedditAdapter(config=config).search("reddit", limit=1)
        if payload["ok"] and payload.get("items"):
            return "ok", "Reddit live OAuth search probe succeeded"
        if payload["ok"]:
            return "warn", "Reddit live probe completed but returned zero items"
        error = payload.get("error")
        return "warn", str((error.get("message") if error else None) or "Reddit live probe failed")

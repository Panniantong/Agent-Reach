"""Helpers for interpreting mcporter's machine-readable config output."""

from __future__ import annotations

import json


def configured_server_names(output: str) -> set[str]:
    """Return configured server names without matching paths or other metadata."""
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return set()

    servers = payload.get("servers", []) if isinstance(payload, dict) else []
    if not isinstance(servers, list):
        return set()

    return {
        name.casefold()
        for server in servers
        if isinstance(server, dict)
        if isinstance(name := server.get("name"), str)
    }

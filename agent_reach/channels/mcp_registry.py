# -*- coding: utf-8 -*-
"""MCP Registry channel checks."""

from __future__ import annotations

from agent_reach.adapters.mcp_registry import MCPRegistryAdapter

from .base import Channel


class MCPRegistryChannel(Channel):
    name = "mcp_registry"
    description = "Model Context Protocol server registry discovery"
    backends = ["MCP Registry API"]
    tier = 2
    auth_kind = "none"
    entrypoint_kind = "python"
    operations = ["search", "read"]
    operation_inputs = {
        "search": "query",
        "read": "registry_server",
    }
    host_patterns = ["https://registry.modelcontextprotocol.io/*"]
    example_invocations = [
        'agent-reach collect --channel mcp_registry --operation search --input "docs mcp" --limit 10 --json',
        'agent-reach collect --channel mcp_registry --operation read --input "ac.tandem/docs-mcp" --json',
    ]
    supports_probe = True
    install_hints = [
        "No local install is required. The public MCP Registry API is read without authentication.",
    ]

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        host = urlparse(url).netloc.lower()
        return host == "registry.modelcontextprotocol.io"

    def check(self, config=None):
        return "ok", "Public MCP Registry API is available without local configuration"

    def probe(self, config=None):
        payload = MCPRegistryAdapter(config=config).search("mcp", limit=1)
        if payload["ok"] and payload.get("items"):
            return "ok", "MCP Registry live search probe succeeded"
        if payload["ok"]:
            return "warn", "MCP Registry live probe completed but returned zero items"
        error = payload.get("error")
        return "warn", str((error.get("message") if error else None) or "MCP Registry live probe failed")

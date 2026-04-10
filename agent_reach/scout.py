# -*- coding: utf-8 -*-
"""Capability-only scout helpers."""

from __future__ import annotations

from typing import Any

from agent_reach.channels import get_all_channel_contracts
from agent_reach.config import Config
from agent_reach.doctor import check_all
from agent_reach.schemas import SCHEMA_VERSION, utc_timestamp

BUDGETS = ("auto", "small", "medium", "large", "xlarge")
QUALITY_PROFILES = ("precision", "balanced", "recall")
PRESETS = (
    "broad-web",
    "oss-watch",
    "japan-tech",
    "social-pulse",
    "feed-watch",
    "research-papers",
    "security",
)

_PRESET_CHANNELS = {
    "broad-web": ("exa_search", "searxng", "hacker_news", "reddit", "web", "crawl4ai"),
    "oss-watch": ("github", "mcp_registry", "hacker_news", "exa_search", "searxng", "web", "crawl4ai"),
    "japan-tech": ("qiita", "hatena_bookmark", "searxng", "web"),
    "social-pulse": ("bluesky", "reddit", "twitter"),
    "feed-watch": ("rss", "hacker_news", "searxng", "web", "crawl4ai"),
    "research-papers": ("exa_search", "searxng", "web", "crawl4ai"),
    "security": ("github", "mcp_registry", "hacker_news", "exa_search", "searxng", "rss", "web", "crawl4ai"),
}


class ScoutPlanError(Exception):
    """Raised when scout plan input is invalid."""


def build_scout_plan(
    topic: str,
    *,
    budget: str = "auto",
    quality: str = "precision",
    preset: str | None = None,
    config: Config | None = None,
) -> dict[str, Any]:
    """Build a network-free capability snapshot for external callers."""

    text = topic.strip()
    if not text:
        raise ScoutPlanError("topic must not be empty")
    if budget not in BUDGETS:
        raise ScoutPlanError(f"Unsupported budget: {budget}")
    if quality not in QUALITY_PROFILES:
        raise ScoutPlanError(f"Unsupported quality profile: {quality}")
    if preset is not None and preset not in PRESETS:
        raise ScoutPlanError(f"Unsupported preset: {preset}")

    config = config or Config()
    contracts = get_all_channel_contracts()
    readiness = check_all(config, probe=False)

    available_channels: list[dict[str, Any]] = []
    ready_channels: list[str] = []
    not_ready_channels: list[dict[str, str]] = []
    for contract in contracts:
        channel_payload = readiness.get(contract["name"], {})
        available_channels.append(
            {
                "channel": contract["name"],
                "description": contract["description"],
                "tier": contract["tier"],
                "operations": contract.get("operations", []),
                "operation_contracts": contract.get("operation_contracts", {}),
                "supports_probe": contract.get("supports_probe", False),
                "status": channel_payload.get("status", "unknown"),
                "message": channel_payload.get("message", ""),
            }
        )
        if channel_payload.get("status") == "ok":
            ready_channels.append(contract["name"])
        else:
            not_ready_channels.append(
                {
                    "channel": contract["name"],
                    "status": channel_payload.get("status", "unknown"),
                    "message": channel_payload.get("message", ""),
                }
            )

    known_channels = {contract["name"] for contract in contracts}
    preset_channels = _PRESET_CHANNELS[preset] if preset is not None else ()
    unknown_seed_channels = [channel for channel in preset_channels if channel not in known_channels]
    if unknown_seed_channels:
        raise ScoutPlanError(
            "Preset references unknown channel(s): "
            + ", ".join(unknown_seed_channels)
        )
    seed_channels = list(preset_channels)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_timestamp(),
        "command": "scout",
        "plan_only": True,
        "topic": text,
        "budget": budget,
        "budget_requested": budget,
        "quality_profile": quality,
        "preset": preset,
        "available_channels": available_channels,
        "ready_channels": ready_channels,
        "not_ready_channels": not_ready_channels,
        "seed_channels": seed_channels,
        "required_readiness_checks": _readiness_checks(available_channels),
    }


def render_scout_text(payload: dict[str, Any]) -> str:
    """Render a capability snapshot for humans."""

    lines = [
        "Agent Reach Scout Capability Snapshot",
        "========================================",
        f"Topic: {payload['topic']}",
        f"Budget hint: {payload['budget']}",
        f"Quality: {payload['quality_profile']}",
        f"Ready channels: {', '.join(payload['ready_channels']) or 'none'}",
    ]
    if payload["seed_channels"]:
        lines.append(f"Seed channels: {', '.join(payload['seed_channels'])}")
    if payload["not_ready_channels"]:
        lines.append("Not ready:")
        for channel in payload["not_ready_channels"]:
            lines.append(f"  - {channel['channel']}: {channel['status']} - {channel['message']}")
    return "\n".join(lines)


def _readiness_checks(channels: list[dict[str, Any]]) -> list[str]:
    checks = ["agent-reach channels --json", "agent-reach doctor --json"]
    if any(channel.get("supports_probe") for channel in channels):
        checks.append("agent-reach doctor --json --probe")
    return checks

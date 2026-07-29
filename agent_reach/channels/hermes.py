"""Read-only inspection of Hermes MCP configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from agent_reach.utils.paths import PrivatePathError, read_small_text_no_follow

_MAX_CONFIG_BYTES = 1024 * 1024


class HermesConfigError(ValueError):
    """Raised when Hermes MCP configuration cannot be inspected safely."""


@dataclass(frozen=True)
class HermesMcpConfigInspection:
    """Minimal non-secret facts from Hermes MCP configuration."""

    server_names: frozenset[str]
    source: str | None


def _hermes_config_path() -> Path:
    configured_home = os.environ.get("HERMES_HOME", "").strip()
    if configured_home:
        home = Path(os.path.abspath(os.path.expanduser(configured_home)))
    else:
        home = Path.home() / ".hermes"
    return home / "config.yaml"


def inspect_hermes_mcp_config() -> HermesMcpConfigInspection:
    """Read enabled Hermes MCP names without starting servers or reading secrets."""
    config_path = _hermes_config_path()
    if not os.path.lexists(config_path):
        return HermesMcpConfigInspection(frozenset(), None)

    try:
        raw = read_small_text_no_follow(config_path, max_bytes=_MAX_CONFIG_BYTES)
    except PrivatePathError as exc:
        raise HermesConfigError(f"Hermes 配置文件无法安全读取：{exc}") from exc
    except (OSError, UnicodeError) as exc:
        raise HermesConfigError("Hermes 配置文件无法安全读取") from exc
    if raw is None:
        return HermesMcpConfigInspection(frozenset(), None)

    try:
        payload = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise HermesConfigError("Hermes 配置不是有效的 UTF-8 YAML") from exc
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise HermesConfigError("Hermes 配置顶层必须是对象")

    servers = payload.get("mcp_servers", {})
    if not isinstance(servers, dict):
        raise HermesConfigError("Hermes 配置的 mcp_servers 必须是对象")

    names = set()
    for name, definition in servers.items():
        if not isinstance(name, str) or not name.strip():
            raise HermesConfigError("Hermes 配置包含无效的 server name")
        if not isinstance(definition, dict):
            raise HermesConfigError("Hermes MCP server 定义必须是对象")
        enabled = definition.get("enabled", True)
        if not isinstance(enabled, bool):
            raise HermesConfigError("Hermes MCP server 的 enabled 必须是布尔值")
        if enabled:
            names.add(name.casefold())

    return HermesMcpConfigInspection(frozenset(names), str(config_path))

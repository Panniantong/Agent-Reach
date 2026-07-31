"""Read-only helpers for interpreting mcporter configuration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from agent_reach.utils.paths import (
    PrivatePathError,
    read_small_text_no_follow,
    user_home,
)

_MAX_CONFIG_BYTES = 1024 * 1024
_MISSING = object()


class McporterConfigError(ValueError):
    """Raised when mcporter configuration is not trustworthy."""


@dataclass(frozen=True)
class McporterConfigInspection:
    """Minimal, non-secret routing facts from one mcporter config layer."""

    server_names: frozenset[str]
    source: str | None
    imports_unchecked: bool = False


def inspect_mcporter_config(
    root_dir: str | Path | None = None,
) -> McporterConfigInspection:
    """Read the effective local mcporter config without starting mcporter.

    An explicit ``MCPORTER_CONFIG`` is a single layer. Otherwise mcporter
    0.7.3 loads the first home config
    (``~/.mcporter/mcporter.json`` / ``mcporter.jsonc``) and then
    ``<cwd>/config/mcporter.json``; project entries override duplicate home
    names. Only exact ``mcpServers`` keys are returned. Editor imports are
    deliberately not opened because Doctor must not expand its
    credential-read boundary.
    """
    selected_layers = _select_config_layers(root_dir)
    if not selected_layers:
        return McporterConfigInspection(frozenset(), None)

    names = set()
    imports_unchecked = False
    sources = []
    for config_path, source in selected_layers:
        payload = _read_config_object(config_path)
        servers = payload.get("mcpServers")
        if not isinstance(servers, dict):
            raise McporterConfigError("mcporter 配置缺少 mcpServers 对象")

        for name, definition in servers.items():
            if not isinstance(name, str) or not name.strip():
                raise McporterConfigError("mcporter 配置包含无效的 server name")
            if not isinstance(definition, dict):
                raise McporterConfigError("mcporter server 定义必须是对象")
            names.add(name.casefold())

        imports = payload.get("imports", _MISSING)
        if imports is _MISSING:
            # mcporter defaults to importing supported editor configs when the
            # key is omitted. Doctor intentionally does not open those files.
            imports_unchecked = True
        elif not isinstance(imports, list) or not all(
            isinstance(item, str) for item in imports
        ):
            raise McporterConfigError("mcporter imports 必须是字符串列表")
        elif imports:
            imports_unchecked = True
        sources.append(source)

    return McporterConfigInspection(
        frozenset(names),
        "+".join(sources),
        imports_unchecked=imports_unchecked,
    )


def _select_config_layers(
    root_dir: str | Path | None,
) -> list[tuple[Path, str]]:
    root = Path(os.path.abspath(os.fspath(root_dir or Path.cwd())))
    explicit = os.environ.get("MCPORTER_CONFIG", "").strip()
    if explicit:
        expanded = Path(os.path.expanduser(explicit))
        if not expanded.is_absolute():
            expanded = root / expanded
        return [(Path(os.path.abspath(os.fspath(expanded))), "explicit")]

    layers = []
    home_base = user_home() / ".mcporter"
    for name in ("mcporter.json", "mcporter.jsonc"):
        candidate = home_base / name
        if os.path.lexists(candidate):
            layers.append((candidate, "home"))
            break

    project_path = root / "config" / "mcporter.json"
    if os.path.lexists(project_path):
        layers.append((project_path, "project"))
    return layers


def _read_config_object(config_path: Path) -> dict:
    try:
        raw = read_small_text_no_follow(
            config_path,
            max_bytes=_MAX_CONFIG_BYTES,
        )
    except PrivatePathError as exc:
        raise McporterConfigError(
            f"mcporter 配置文件无法安全读取：{exc}"
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise McporterConfigError("mcporter 配置文件无法安全读取") from exc
    if raw is None:
        raise McporterConfigError("mcporter 配置文件不存在")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise McporterConfigError("mcporter 配置不是有效的 UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise McporterConfigError("mcporter 配置顶层必须是对象")
    return payload


def configured_server_names(output: str) -> set[str]:
    """Return exact configured server names from ``mcporter ... --json``.

    Paths, descriptions, endpoints, and other metadata are deliberately
    ignored: only each server object's ``name`` field is a routing signal.
    """
    try:
        payload = json.loads(output)
    except (json.JSONDecodeError, TypeError) as exc:
        raise McporterConfigError("mcporter 返回的 JSON 无法解析") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("servers"), list):
        raise McporterConfigError("mcporter JSON 缺少 servers 列表")

    return {
        name.casefold()
        for server in payload["servers"]
        if isinstance(server, dict)
        if isinstance(name := server.get("name"), str) and name.strip()
    }

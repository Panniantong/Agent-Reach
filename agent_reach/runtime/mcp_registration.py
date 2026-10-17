"""Install the local Reach MCP entry in an existing Cursor profile."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from agent_reach.utils.paths import atomic_write_private_text, home_dir, read_small_text_no_follow

from . import state
from .result import NEED_SETUP, ReachError

SERVER = "agent-reach"


def _path() -> Path:
    return home_dir() / ".cursor" / "mcp.json"


def _load(path: Path) -> dict:
    try:
        raw = read_small_text_no_follow(path, max_bytes=1024 * 1024)
        data = json.loads(raw) if raw else {}
    except (OSError, ValueError) as exc:
        raise ReachError(NEED_SETUP, "Cursor MCP config is unreadable; left it unchanged") from exc
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
        raise ReachError(NEED_SETUP, "Cursor MCP config has an invalid server map; left it unchanged")
    return data


def status() -> dict:
    path = _path()
    if not path.parent.is_dir():
        return {"agent": "cursor", "installed": False, "reason": "Cursor config directory is absent"}
    data = _load(path)
    return {"agent": "cursor", "installed": SERVER in data.get("mcpServers", {}),
            "path": str(path), "server": SERVER}


def install() -> dict:
    path = _path()
    if not path.parent.is_dir():
        raise ReachError(NEED_SETUP, "Cursor config directory is absent")
    exe = shutil.which("agent-reach")
    if not exe:
        raise ReachError(NEED_SETUP, "Install the agent-reach executable before registering MCP")
    entry = {"command": str(Path(exe).absolute()), "args": ["mcp"]}
    data = _load(path)
    servers = data.setdefault("mcpServers", {})
    previous = servers.get(SERVER)
    owned = state.load().get("mcp", {}).get("cursor", {})
    if previous is not None and previous != entry and not (
        owned.get("path") == str(path) and owned.get("entry") == previous
    ):
        raise ReachError(NEED_SETUP, "Cursor already has a different agent-reach MCP entry; left it unchanged")
    servers[SERVER] = entry
    atomic_write_private_text(path, json.dumps(data, indent=2, ensure_ascii=False))
    state.mutate(lambda saved: saved.setdefault("mcp", {}).__setitem__(
        "cursor", {"path": str(path), "entry": entry}))
    return {"agent": "cursor", "installed": True, "path": str(path), "server": SERVER}


def uninstall(*, dry_run: bool = False) -> dict:
    path = _path()
    record = state.load().get("mcp", {}).get("cursor")
    if not record or record.get("path") != str(path):
        return {"agent": "cursor", "removed": False}
    data = _load(path)
    servers = data.get("mcpServers", {})
    if servers.get(SERVER) != record.get("entry"):
        return {"agent": "cursor", "removed": False, "reason": "Entry was changed by the user"}
    if not dry_run:
        servers.pop(SERVER)
        atomic_write_private_text(path, json.dumps(data, indent=2, ensure_ascii=False))
        state.mutate(lambda saved: saved.setdefault("mcp", {}).pop("cursor", None))
    return {"agent": "cursor", "removed": True, "dry_run": dry_run}

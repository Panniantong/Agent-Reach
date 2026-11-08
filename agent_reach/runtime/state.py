"""~/.agent-reach/state.json: which channels are added, which tools we installed, last checks.

    {
      "version": 1,
      "channels": {"bilibili": {"added_at": "..."}},
      "removed_defaults": ["youtube"],
      "tools": {"bili-cli": {"owner": "agent-reach" | "user", "scope": "private" | "global", "version": "0.6.2"}},
      "checks": {"bilibili": {"at": "...", "actions": {"search": true}, "previous": {"search": true}}},
      "skill": {"links": [{"agent": "claude-code", "path": "...", "kind": "link" | "copy"}]}
    }

`owner` decides what remove/sync/uninstall may delete: only "agent-reach" entries.
`version` is the version actually installed (tools are not pinned).
`removed_defaults` are default channels the user removed; setup and update leave them out.
`skill.links` are the skill links/copies we made; update refreshes them, uninstall removes them.
"""

from __future__ import annotations

import datetime as _dt
import json
import time
from pathlib import Path
from typing import Callable, TypeVar

from agent_reach.utils.paths import (
    PrivatePathError,
    atomic_write_private_text,
    home_dir,
    make_private_dir,
    read_small_text_no_follow,
)

STATE_VERSION = 1
T = TypeVar("T")


def root() -> Path:
    return home_dir() / ".agent-reach"


def state_path() -> Path:
    return root() / "state.json"


def exists() -> bool:
    return state_path().is_file()


def load() -> dict:
    try:
        text = read_small_text_no_follow(state_path(), max_bytes=1024 * 1024)
        data = json.loads(text) if text else {}
    except (OSError, ValueError, PrivatePathError):
        data = {}
    data.setdefault("version", STATE_VERSION)
    for key in ("channels", "tools", "checks", "skill"):
        data.setdefault(key, {})
    data["skill"].setdefault("links", [])
    if not isinstance(data.get("removed_defaults"), list):
        data["removed_defaults"] = []
    return data


def save(data: dict) -> None:
    data.setdefault("owned_paths", {})["state.json"] = "state ledger"
    import hashlib
    name = hashlib.sha256(b"reach-state-write").hexdigest() + ".lock"
    data["owned_paths"]["browser-locks/" + name] = "state lock"
    make_private_dir(root())
    atomic_write_private_text(state_path(), json.dumps(data, indent=2, ensure_ascii=False))


def mutate(change: Callable[[dict], T]) -> T:
    """Serialize short state read-modify-write operations across CLI processes."""
    from .browser_binding import execution_lock
    from .result import ReachError

    for _ in range(100):
        try:
            with execution_lock("reach-state-write"):
                data = load()
                result = change(data)
                save(data)
                return result
        except ReachError as exc:
            if exc.code != "BUSY":
                raise
            time.sleep(0.05)
    raise ReachError("BUSY", "Reach state is being updated by another command")


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def age_seconds(iso: str) -> float:
    try:
        then = _dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    except (TypeError, ValueError):
        return float("inf")
    return (_dt.datetime.now(_dt.timezone.utc) - then).total_seconds()


def owned_path(path: Path, data: dict | None = None) -> bool:
    """Deletion permission comes from the ledger, never a familiar filename."""
    try:
        relative = Path(path).absolute().relative_to(root().absolute()).as_posix()
    except ValueError:
        return False
    return relative in (data if data is not None else load()).get("owned_paths", {})


def remember_path(path: Path, purpose: str) -> None:
    from agent_reach.utils.paths import ensure_no_symlink_path

    ensure_no_symlink_path(path, "owned path")
    relative = Path(path).absolute().relative_to(root().absolute()).as_posix()
    if relative in {".", ""} or ".." in Path(relative).parts:
        raise ValueError("Cannot own the entire Reach root")
    if owned_path(path):
        return
    mutate(lambda data: data.setdefault("owned_paths", {}).update({relative: purpose}))

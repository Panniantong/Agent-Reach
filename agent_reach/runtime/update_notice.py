"""Background "new version" notice.

Commands never wait on the network. At most once per 24 h a command starts a
short detached process (`python -m agent_reach.runtime.update_notice`) that
reads the latest GitHub release (10 s timeout) and writes
~/.agent-reach/update-check.json {checked_at, latest, notes}. No network = no
file change, silently. `notice()` reads that cache only: it returns
{current, latest, notes} when the cached latest is newer than this version.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

from agent_reach import __version__
from agent_reach.utils.paths import (
    PrivatePathError,
    atomic_write_private_text,
    make_private_dir,
    read_small_text_no_follow,
)

from . import state

REPO = "Panniantong/Agent-Reach"
INTERVAL = 24 * 3600
FETCH_TIMEOUT = 10.0
NOTES_MAX = 2000
#: Set to any value to never start the background check (tests, CI).
DISABLE_ENV = "AGENT_REACH_NO_UPDATE_CHECK"


def cache_path() -> Path:
    return state.root() / "update-check.json"


def started_path() -> Path:
    """Touched when a background check starts: limits starts to one per INTERVAL, online or not."""
    return state.root() / "update-check.started"


def version_tuple(v: str) -> tuple:
    try:
        return tuple(int(x) for x in str(v).strip().lstrip("v").split("."))
    except ValueError:
        return ()


def fetch_latest(timeout: float = FETCH_TIMEOUT) -> dict:
    """{latest, notes} of the latest GitHub release. Raises on network errors."""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"User-Agent": "agent-reach", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        rel = json.loads(resp.read())
    return {"latest": str(rel.get("tag_name", "")).lstrip("v"), "notes": (rel.get("body") or "")[:NOTES_MAX]}


def write_cache(info: dict) -> None:
    make_private_dir(state.root())
    atomic_write_private_text(cache_path(), json.dumps(
        {"checked_at": state.now(), "latest": info["latest"], "notes": info["notes"]}, ensure_ascii=False))


def read_cache() -> Optional[dict]:
    try:
        data = json.loads(read_small_text_no_follow(cache_path(), max_bytes=64 * 1024) or "null")
    except (OSError, ValueError, PrivatePathError):
        return None
    return data if isinstance(data, dict) else None


def notice() -> Optional[dict]:
    """{current, latest, notes} when the cached latest release is newer than this version."""
    data = read_cache()
    if not data:
        return None
    latest = str(data.get("latest") or "")
    current = version_tuple(__version__)
    if not current or version_tuple(latest) <= current:
        return None
    return {"current": __version__, "latest": latest, "notes": str(data.get("notes") or "")}


def _due() -> bool:
    try:
        return time.time() - started_path().stat().st_mtime >= INTERVAL
    except OSError:
        return True


def maybe_refresh() -> None:
    """Start the detached background check if the last one began over 24 h ago. Never blocks or raises."""
    if os.environ.get(DISABLE_ENV) or not _due():
        return
    try:
        make_private_dir(state.root())
        started_path().touch()
        kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                        "close_fds": True, "cwd": str(state.root())}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen([sys.executable, "-m", "agent_reach.runtime.update_notice"], **kwargs)
    except (OSError, PrivatePathError):
        pass


def _main() -> int:
    try:
        write_cache(fetch_latest())
    except Exception:  # noqa: BLE001 - offline or GitHub down: stay silent
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())

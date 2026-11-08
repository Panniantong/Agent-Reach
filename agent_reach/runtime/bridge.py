"""Official OpenCLI Bridge, supervised only while the dedicated browser is open.

No upstream edits. Existing compatible user processes are borrowed, never killed.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

from . import tools
from .result import NEED_SETUP, ReachError

URL = "http://127.0.0.1:19825"


def status() -> dict:
    request = urllib.request.Request(URL + "/status", headers={"X-OpenCLI": "1"})
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=1) as response:
            value = json.loads(response.read(128 * 1024))
        return value if isinstance(value, dict) and value.get("ok") else {}
    except (OSError, ValueError):
        return {}


def launch_spec() -> tuple[list[str], str]:
    exe = tools.resolve("opencli")
    node = tools.resolve("node")
    if not exe or not node:
        raise ReachError(NEED_SETUP, "Run agent-reach add CHANNEL to install Node and OpenCLI")
    resolved = Path(exe).resolve()
    # npm on Windows uses a .cmd shim beside node_modules; POSIX uses a symlink.
    candidates = [*resolved.parents, Path(exe).parent / "node_modules" / "@jackwener" / "opencli"]
    for root in candidates:
        daemon = root / "dist" / "src" / "daemon.js"
        package = root / "package.json"
        if daemon.is_file() and package.is_file():
            return [node, str(daemon)], str(json.loads(package.read_text("utf-8"))["version"])
    raise ReachError(NEED_SETUP, "Unsupported OpenCLI package layout; reinstall official OpenCLI")


def require_compatible() -> dict:
    """Do not let upstream CLI auto-restart an unrelated older daemon."""
    _, version = launch_spec()
    current = status()
    if current and current.get("daemonVersion") != version:
        raise ReachError(NEED_SETUP, "An OpenCLI Bridge of another version is running; left it unchanged",
                         hint="Close that OpenCLI session yourself, then retry. Reach will not restart it.")
    return current


def require_running() -> dict:
    """Distinguish an unavailable Bridge from a site with no saved cookies."""
    current = require_compatible()
    if not current:
        raise ReachError(NEED_SETUP, "OpenCLI Bridge is not running; the site login could not be inspected",
                         hint="Run agent-reach browser setup to reconnect the Bridge, then retry.")
    return current


def start():
    """Return a child handle only when Reach started this process."""
    argv, _ = launch_spec()
    if require_compatible():
        return None
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        current = require_compatible()
        if current:
            if current.get("pid") == proc.pid:
                return proc
            proc.wait(timeout=5)  # another starter won the port; never claim its process
            return None
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    proc.terminate()
    proc.wait(timeout=5)
    raise ReachError(NEED_SETUP, "OpenCLI Bridge could not start alongside the dedicated browser")


def close(proc) -> None:
    """Reap only our child, unconditionally bounded to the dedicated browser."""
    if proc is None:
        return
    # Existing user daemons never have a Popen handle here. Other clients may
    # reconnect through upstream after our browser-scoped child exits.
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

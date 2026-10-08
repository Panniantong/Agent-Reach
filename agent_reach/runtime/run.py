"""Bounded calls to upstream tools: subprocesses and HTTP."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import urllib.request
from pathlib import Path
from typing import Mapping, Optional, Sequence

from agent_reach.utils.process import utf8_subprocess_env

from .result import NEED_SETUP, TIMEOUT, ReachError, _clean

_DEFAULT_MAX_BYTES = 8 * 1024 * 1024


class CommandFailed(ReachError):
    """Upstream exited non-zero. Channels may re-map it using `stderr`."""

    def __init__(self, code: str, message: str, stderr: str = "", stdout: str = ""):
        super().__init__(code, message)
        self.stderr = stderr
        self.stdout = stdout


def run_cmd(
    argv: Sequence[str],
    *,
    timeout: float,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[str] = None,
    label: Optional[str] = None,
) -> str:
    """Run an upstream command and return stdout.

    Runs from the user's home by default so tools never pick up config from
    whatever project the agent happens to be in. On timeout the whole process
    group is killed.
    """
    name = label or Path(argv[0]).name
    exe = shutil.which(argv[0])
    if not exe:
        raise ReachError(NEED_SETUP, f"{name} is not installed")
    run_env = utf8_subprocess_env()
    if env:
        run_env.update(env)
    proc = subprocess.Popen(
        [exe, *argv[1:]],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env=run_env,
        cwd=cwd or os.path.expanduser("~"),
        start_new_session=(os.name != "nt"),
    )
    try:
        out, err = proc.communicate(timeout=max(timeout, 0.1))
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            proc.kill()
        proc.communicate()
        raise ReachError(TIMEOUT, f"{name} did not finish within {timeout:.0f}s")
    stdout = out.decode("utf-8", errors="replace")
    stderr = err.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        last = next((ln for ln in reversed(stderr.splitlines()) if ln.strip()), "")
        raise CommandFailed(
            "UPSTREAM_BROKEN",
            f"{name} exited {proc.returncode}: {_clean(last) or 'no error output'}",
            stderr=stderr,
            stdout=stdout,
        )
    return stdout


def http_request(
    url: str,
    *,
    timeout: float,
    data: Optional[bytes] = None,
    headers: Optional[Mapping[str, str]] = None,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> bytes:
    """GET (or POST when `data` is given) with a size cap. Errors propagate to classify()."""
    merged = {"User-Agent": "agent-reach"}
    merged.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=merged)
    with urllib.request.urlopen(req, timeout=max(timeout, 0.1)) as resp:
        body = resp.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ReachError("UPSTREAM_BROKEN", f"response exceeds {max_bytes} bytes")
    return body

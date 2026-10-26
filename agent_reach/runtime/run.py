"""Bounded calls to upstream tools: subprocesses and HTTP."""

from __future__ import annotations

import http.client
import os
import re
import signal
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Mapping, Optional, Sequence

from agent_reach.utils.process import utf8_subprocess_env

from .result import BAD_INPUT, NEED_SETUP, TIMEOUT, ReachError, _clean

_DEFAULT_MAX_BYTES = 8 * 1024 * 1024
_NPM_SHIM_SCRIPT = re.compile(r'"%dp0%\\(?P<script>[^"\r\n]*?\.(?:cjs|mjs|js))"', re.IGNORECASE)
_CMD_METACHARS = frozenset('&|<>^()%!"\r\n')


def _windows_argv(exe: str, args: Sequence[str], *, node: Optional[str]) -> list[str]:
    """Avoid cmd.exe parsing arguments passed to Windows batch shims.

    npm installs ``.cmd`` launchers even for JavaScript entry points. Running
    their JS file with Node directly preserves arguments such as URLs containing
    ``&``. Unknown batch files stay usable for ordinary arguments, but reject
    cmd.exe metacharacters instead of silently splitting or expanding them.
    """
    if not exe.lower().endswith((".cmd", ".bat")):
        return [exe, *args]

    try:
        shim = Path(exe).read_text(encoding="utf-8", errors="replace")
    except OSError:
        shim = ""
    match = _NPM_SHIM_SCRIPT.search(shim)
    if match and node and Path(node).is_file():
        relative = match.group("script").replace("\\", os.sep)
        script = Path(exe).parent / relative
        if script.is_file():
            return [node, str(script), *args]

    if any(char in _CMD_METACHARS for arg in args for char in str(arg)):
        raise ReachError(
            BAD_INPUT,
            f"{Path(exe).name} cannot safely receive arguments containing cmd.exe metacharacters",
        )
    return [exe, *args]


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
    input_data: Optional[str] = None,
) -> str:
    """Run an upstream command and return stdout.

    Runs from the user's home by default so tools never pick up config from
    whatever project the agent happens to be in. On timeout the whole process
    group is killed.
    """
    from .tools import resolve

    name = label or Path(argv[0]).name
    exe = resolve(argv[0]) if not os.path.isabs(argv[0]) else (argv[0] if os.path.exists(argv[0]) else None)
    if not exe:
        raise ReachError(NEED_SETUP, f"{name} is not installed")
    run_env = utf8_subprocess_env()
    if env:
        run_env.update(env)
    # The local API worker is already in a supervised process group. Keep its
    # children there so the API's hard deadline can stop the entire execution.
    supervised = os.environ.get("REACH_API_SUPERVISED") == "1"
    child_argv = [exe, *argv[1:]]
    if sys.platform == "win32" and exe.lower().endswith((".cmd", ".bat")):
        child_argv = _windows_argv(exe, argv[1:], node=resolve("node"))
    proc = subprocess.Popen(
        child_argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
        env=run_env,
        cwd=cwd or os.path.expanduser("~"),
        start_new_session=(sys.platform != "win32" and not supervised),
    )
    try:
        kwargs = {"input": input_data.encode("utf-8")} if input_data is not None else {}
        out, err = proc.communicate(timeout=max(timeout, 0.1), **kwargs)
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            # Kill this command's descendants too (Playwright driver + Chrome).
            # Killing only Python leaves the profile locked by orphan browsers.
            taskkill = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/taskkill.exe")
            try:
                subprocess.run([taskkill, "/PID", str(proc.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=5, check=False)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()
        elif not supervised:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            proc.kill()
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            # A descendant may still own a pipe; never wait indefinitely.
            if proc.stdout is not None:
                proc.stdout.close()
            if proc.stderr is not None:
                proc.stderr.close()
            proc.wait(timeout=5)
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
        declared = getattr(resp, "headers", {}).get("Content-Length", "")
        if isinstance(declared, str) and declared.strip().isdigit() and len(body) <= max_bytes:
            expected = int(declared)
            if len(body) < expected:
                # A bounded read can silently return a short body on early EOF.
                raise http.client.IncompleteRead(body, expected - len(body))
    if len(body) > max_bytes:
        raise ReachError("UPSTREAM_BROKEN", f"response exceeds {max_bytes} bytes")
    return body

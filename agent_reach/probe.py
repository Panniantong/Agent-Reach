# -*- coding: utf-8 -*-
"""Lightweight upstream command probing.

Distinguishes the three failure modes that look identical to shutil.which():
  - missing: command not on PATH
  - broken: command exists but cannot execute — most commonly a stale venv
    shebang after a system Python upgrade (pipx/uv tool installs break this
    way: which() finds the shim, but exec fails with FileNotFoundError
    pointing at the shim itself)
  - timeout/error: command runs but misbehaves

Channels use probe_command() inside check() so doctor reports real health,
not just file existence.
"""

import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional, Sequence

from agent_reach.utils.process import utf8_subprocess_env

#: Exit codes shells use for "found but not executable" / "not found".
_BROKEN_EXIT_CODES = (126, 127)


@dataclass
class ProbeResult:
    status: str  # "ok" | "missing" | "broken" | "timeout" | "error"
    output: str = ""
    hint: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def reinstall_hint(package: str) -> str:
    """Prescription for a broken (stale-venv) CLI install."""
    return (
        f"Command exists but can't execute — usually venv interpreter lost after system Python upgrade. Reinstall to fix:\n"
        f"  uv tool install --force {package}\n"
        f"or: pipx reinstall {package}"
    )


def probe_command(
    cmd: str,
    args: Sequence[str] = ("--version",),
    timeout: int = 10,
    retries: int = 0,
    package: Optional[str] = None,
) -> ProbeResult:
    """Actually execute `cmd *args` and classify the result.

    Intended for SIDE-EFFECT-FREE health probes only (version/status
    commands): retries re-run the command verbatim with no backoff, so a
    non-idempotent command would repeat its effect.

    package: pip/pipx package name used in the broken-install hint
             (defaults to cmd).
    """
    path = shutil.which(cmd)
    if not path:
        return ProbeResult("missing")

    last: Optional[ProbeResult] = None
    for _ in range(retries + 1):
        last = _run_once(path, args, timeout, package or cmd)
        if last.ok:
            return last
        # missing/broken won't heal between retries — only transient
        # failures (timeout/error) are worth a second attempt
        if last.status in ("missing", "broken"):
            return last
    return last


def _run_once(path: str, args: Sequence[str], timeout: int, package: str) -> ProbeResult:
    try:
        r = subprocess.run(
            [path, *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=utf8_subprocess_env(),
        )
    except FileNotFoundError:
        # which() found it but exec failed: the shebang interpreter is gone
        return ProbeResult("broken", hint=reinstall_hint(package))
    except OSError:
        return ProbeResult("broken", hint=reinstall_hint(package))
    except subprocess.TimeoutExpired:
        return ProbeResult("timeout", hint=f"`{path}` timed out (>{timeout}s)")

    if r.returncode in _BROKEN_EXIT_CODES:
        return ProbeResult("broken", hint=reinstall_hint(package))

    output = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        return ProbeResult("error", output=output.strip())
    return ProbeResult("ok", output=output.strip())

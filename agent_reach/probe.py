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
import time
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from agent_reach.utils.process import utf8_subprocess_env

#: Exit codes shells use for "found but not executable" / "not found".
_BROKEN_EXIT_CODES = (126, 127)

#: Default time-to-live for a cached probe result, in seconds.
_DEFAULT_PROBE_TTL_SECONDS = 10.0

#: Process-wide probe cache: key -> (expires_at, ProbeResult).
#: Channels and doctor share this cache so repeated `agent-reach doctor`
#: runs within the TTL window reuse fresh results instead of re-executing
#: every upstream CLI. `clear_probe_cache()` forces a full re-probe.
_PROBE_CACHE: dict = {}


def clear_probe_cache() -> None:
    """Drop all cached probe results (used by `doctor --refresh`)."""
    _PROBE_CACHE.clear()


def _cache_get(key: tuple) -> Optional["ProbeResult"]:
    entry = _PROBE_CACHE.get(key)
    if entry is None:
        return None
    expires_at, result = entry
    if time.monotonic() >= expires_at:
        _PROBE_CACHE.pop(key, None)
        return None
    return result


def _cache_put(key: tuple, result: "ProbeResult", ttl: float) -> None:
    _PROBE_CACHE[key] = (time.monotonic() + ttl, result)


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
        f"命令存在但无法执行——通常是系统 Python 升级后 venv 解释器丢失。重装即可修复：\n"
        f"  uv tool install --force {package}\n"
        f"或：pipx reinstall {package}"
    )


def probe_command(
    cmd: str,
    args: Sequence[str] = ("--version",),
    timeout: int = 10,
    retries: int = 0,
    package: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    remove_env: Sequence[str] = (),
    use_cache: bool = True,
    ttl: float = _DEFAULT_PROBE_TTL_SECONDS,
) -> ProbeResult:
    """Actually execute `cmd *args` and classify the result.

    Intended for SIDE-EFFECT-FREE health probes only (version/status
    commands): retries re-run the command verbatim with no backoff, so a
    non-idempotent command would repeat its effect.

    package: pip/pipx package name used in the broken-install hint
             (defaults to cmd).
    env: values added only to the probed child process.
    remove_env: inherited variables removed only from the child process.
    use_cache: reuse a probe result from within the TTL window. This keeps
               repeated `doctor` runs cheap; pass use_cache=False (or call
               clear_probe_cache()) for a guaranteed-fresh probe.
    ttl: cache lifetime in seconds. Defaults to a short window so a stale
         backend can never survive long inside a single process.
    """
    path = shutil.which(cmd)
    if not path:
        return ProbeResult("missing")

    cache_key = (path, tuple(args), timeout, tuple(sorted(env.items())) if env else ())
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    last: Optional[ProbeResult] = None
    for _ in range(retries + 1):
        last = _run_once(path, args, timeout, package or cmd, env, remove_env)
        if last.ok:
            break
        # missing/broken won't heal between retries — only transient
        # failures (timeout/error) are worth a second attempt
        if last.status in ("missing", "broken"):
            break
    assert last is not None  # retries + 1 always executes at least once

    if use_cache:
        _cache_put(cache_key, last, ttl)
    return last


def _run_once(
    path: str,
    args: Sequence[str],
    timeout: int,
    package: str,
    env: Optional[Mapping[str, str]] = None,
    remove_env: Sequence[str] = (),
) -> ProbeResult:
    try:
        subprocess_env = utf8_subprocess_env()
        for key in remove_env:
            subprocess_env.pop(key, None)
        if env:
            subprocess_env.update(env)
        r = subprocess.run(
            [path, *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=subprocess_env,
        )
    except FileNotFoundError:
        # which() found it but exec failed: the shebang interpreter is gone
        return ProbeResult("broken", hint=reinstall_hint(package))
    except OSError:
        return ProbeResult("broken", hint=reinstall_hint(package))
    except subprocess.TimeoutExpired:
        return ProbeResult("timeout", hint=f"`{path}` 响应超时（>{timeout}s）")

    if r.returncode in _BROKEN_EXIT_CODES:
        return ProbeResult("broken", hint=reinstall_hint(package))

    output = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        return ProbeResult("error", output=output.strip())
    return ProbeResult("ok", output=output.strip())

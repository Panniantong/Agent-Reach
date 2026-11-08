"""Old (1.5 and earlier) Agent Reach installs: find them and remove only Agent Reach itself.

1.5 was installed with pipx or into `~/.agent-reach-venv`. After the user moves to
the uv install, those copies would keep an old `agent-reach` on PATH, and a later
`pipx upgrade-all` could put 1.5 back. Only Agent Reach's own package is removed;
the user's other tools (twitter-cli, bili, ...) and data are never touched.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from agent_reach.utils.paths import home_dir

_WIN = os.name == "nt"


def _pipx_reported_venvs() -> str:
    """Where the installed pipx keeps its programs (it differs by OS and pipx version)."""
    pipx = shutil.which("pipx")
    if not pipx:
        return ""
    try:
        out = subprocess.run([pipx, "environment", "--value", "PIPX_LOCAL_VENVS"],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (getattr(out, "stdout", "") or "").strip() if getattr(out, "returncode", 1) == 0 else ""


def _pipx_venvs() -> List[Path]:
    home = home_dir()
    local = os.environ.get("LOCALAPPDATA", "")
    venv_dirs = [_pipx_reported_venvs(),
                 os.path.join(os.environ["PIPX_HOME"], "venvs") if os.environ.get("PIPX_HOME") else "",
                 str(home / ".local" / "pipx" / "venvs"),
                 str(home / "Library" / "Application Support" / "pipx" / "venvs"),
                 str(home / ".local" / "share" / "pipx" / "venvs"),
                 os.path.join(local, "pipx", "pipx", "venvs") if local else "",
                 str(home / "pipx" / "venvs")]
    return [Path(d) / "agent-reach" for d in venv_dirs if d]


def _has_agent_reach(venv: Path) -> bool:
    lib = venv / "Lib" / "site-packages" if _WIN else None
    sites = [lib] if lib else sorted((venv / "lib").glob("python*/site-packages"))
    return any((s / "agent_reach").is_dir() for s in sites if s and s.is_dir())


def _python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if _WIN else "bin/python")


def _current() -> Path:
    return Path(sys.prefix).resolve()


def find() -> List[Dict[str, str]]:
    """Old Agent Reach copies other than the one running now."""
    found: List[Dict[str, str]] = []
    seen = set()
    for kind, venv in [("pipx", v) for v in _pipx_venvs()] + [("venv", home_dir() / ".agent-reach-venv")]:
        try:
            real = venv.resolve()
        except OSError:
            continue
        if real in seen or real == _current() or not _has_agent_reach(venv):
            continue
        seen.add(real)
        found.append({"kind": kind, "path": str(venv)})
    return found


def _drop_pipx_shims(venv: Path) -> None:
    """Remove `agent-reach` launchers that still point into the old pipx venv."""
    dirs = {os.environ.get("PIPX_BIN_DIR", ""), str(home_dir() / ".local" / "bin")}
    for d in filter(None, dirs):
        shim = Path(d) / ("agent-reach.exe" if _WIN else "agent-reach")
        try:
            if shim.is_symlink() and Path(os.path.realpath(shim)).is_relative_to(venv.resolve()):
                shim.unlink()
        except OSError:
            pass


def _uninstall_package(venv: Path) -> bool:
    python = _python(venv)
    for cmd in ([str(python), "-m", "pip", "uninstall", "-y", "-q", "agent-reach"],
                [shutil.which("uv") or "uv", "pip", "uninstall", "-q", "--python", str(python), "agent-reach"]):
        try:
            if subprocess.run(cmd, capture_output=True, timeout=120).returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False


def remove() -> Dict[str, List[Dict[str, str]]]:
    """Remove old Agent Reach copies. A pipx venv holds only Agent Reach, so it goes away;
    `~/.agent-reach-venv` may hold other packages, so only Agent Reach is uninstalled there."""
    removed, failed = [], []
    for item in find():
        venv = Path(item["path"])
        try:
            if item["kind"] == "pipx":
                _drop_pipx_shims(venv)
                shutil.rmtree(venv)
            elif not _uninstall_package(venv):
                raise OSError("pip uninstall failed")
            removed.append(item)
        except OSError as exc:
            failed.append({**item, "reason": str(exc)[:200]})
    return {"removed": removed, "failed": failed}


def manual_command(item: Dict[str, str]) -> str:
    if item["kind"] == "pipx":
        return "pipx uninstall agent-reach"
    return f"{_python(Path(item['path']))} -m pip uninstall -y agent-reach"

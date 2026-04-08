"""Helpers for locating Windows-installed command line tools."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable, Optional


def find_command(name: str) -> Optional[str]:
    """Return an executable path for a command if one can be found."""

    discovered = shutil.which(name)
    if discovered:
        if os.name == "nt":
            shim_path = Path.home() / ".local" / "bin" / f"{name}.cmd"
            if str(Path(discovered).resolve()).lower() == str(shim_path.resolve()).lower():
                for candidate in _windows_candidates(name):
                    if candidate.exists():
                        return str(candidate)
        return discovered

    if os.name != "nt":
        return None

    for candidate in _windows_candidates(name):
        if candidate.exists():
            return str(candidate)
    return None


def ensure_command_on_path(name: str) -> Optional[str]:
    """Return an executable path and prepend its directory to PATH for this process."""

    executable = find_command(name)
    if not executable:
        return None

    directory = str(Path(executable).parent)
    entries = os.environ.get("PATH", "").split(os.pathsep)
    if directory not in entries:
        os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")
    return executable


def _windows_candidates(name: str) -> Iterable[Path]:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")

    if name == "gh":
        yield Path(program_files) / "GitHub CLI" / "gh.exe"
        yield Path(program_files_x86) / "GitHub CLI" / "gh.exe"
    elif name == "yt-dlp":
        winget_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_root.exists():
            for package_dir in winget_root.glob("yt-dlp.yt-dlp_*"):
                yield package_dir / "yt-dlp.exe"

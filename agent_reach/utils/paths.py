"""Cross-platform path and remediation helpers for yt-dlp."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_mcporter_config_path() -> Path:
    """Return the user-scoped mcporter config file path."""

    return Path.home() / ".mcporter" / "mcporter.json"


def render_mcporter_command(command: str) -> str:
    """Render a Windows-friendly mcporter command using the user config path."""

    return f'mcporter --config "{get_mcporter_config_path()}" {command}'


def get_ytdlp_config_dir() -> Path:
    """Return the recommended yt-dlp user config directory for this OS."""

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "yt-dlp"
        return Path.home() / "AppData" / "Roaming" / "yt-dlp"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "yt-dlp"
    return Path.home() / ".config" / "yt-dlp"


def get_ytdlp_config_path() -> Path:
    """Return the yt-dlp user config file path for this OS."""

    return get_ytdlp_config_dir() / "config"


def render_ytdlp_fix_command() -> str:
    """Return an OS-appropriate command to enable Node.js as yt-dlp JS runtime."""

    config_path = get_ytdlp_config_path()
    if sys.platform == "win32":
        return (
            f"$cfg = '{config_path}'\n"
            "New-Item -ItemType Directory -Force -Path (Split-Path $cfg) | Out-Null\n"
            "if (-not (Test-Path $cfg) -or -not (Select-String -Path $cfg -Pattern '--js-runtimes' -Quiet)) {\n"
            "  Add-Content -Path $cfg -Value '--js-runtimes node'\n"
            "}"
        )
    return (
        f"mkdir -p '{config_path.parent}' && "
        f"grep -qxF -- '--js-runtimes node' '{config_path}' 2>/dev/null || "
        f"printf '%s\n' '--js-runtimes node' >> '{config_path}'"
    )

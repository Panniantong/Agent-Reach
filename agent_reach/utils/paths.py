"""Cross-platform path and remediation helpers for yt-dlp."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def make_private_dir(path: str | Path) -> Path:
    """Create a directory (and parents) restricted to the owner (0o700).

    The leaf directory may hold secrets (cookies, tokens). On POSIX the mode is
    enforced with an explicit chmod because ``mkdir``'s mode argument is masked
    by the umask (commonly yielding world-traversable 0o755). On Windows chmod
    cannot express this and is a no-op; the user-profile ACL already applies.
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p, 0o700)
    except (OSError, NotImplementedError):
        pass
    return p


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

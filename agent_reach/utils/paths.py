"""Cross-platform path and remediation helpers."""

from __future__ import annotations

import os
import shlex
import stat
import sys
import tempfile
from pathlib import Path


class PrivatePathError(RuntimeError):
    """Raised when a private write could be redirected through a symlink."""


def ensure_no_symlink_path(path: str | Path, label: str = "路径") -> Path:
    """Reject any existing symlink component without resolving the path."""
    target = Path(path)
    absolute = Path(os.path.abspath(os.fspath(target)))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise PrivatePathError(f"{label}不能经过符号链接：{current}")
    return target


def make_private_dir(path: str | Path) -> Path:
    """Create a directory restricted to the current user where supported."""
    target = ensure_no_symlink_path(path, "私密目录")
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    ensure_no_symlink_path(target, "私密目录")
    if sys.platform != "win32":
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        dir_fd = os.open(target, flags)
        try:
            ensure_no_symlink_path(target, "私密目录")
            if hasattr(os, "fchmod"):
                os.fchmod(dir_fd, 0o700)
        finally:
            os.close(dir_fd)
    return target


def atomic_write_private_text(
    path: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    """Atomically replace a private text file without following symlinks.

    The parent is owner-only, the temporary file is created beside the target
    with mode ``0o600``, and both the parent and target are checked before the
    final rename. ``os.replace`` replaces a late target symlink itself rather
    than following it into another file.
    """
    target = Path(path)
    parent = target.parent
    ensure_no_symlink_path(parent, "父目录")
    make_private_dir(parent)
    ensure_no_symlink_path(parent, "父目录")
    ensure_no_symlink_path(target, "目标文件")

    fd, tmp_name = tempfile.mkstemp(
        dir=str(parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        if os.name != "nt" and hasattr(os, "fchmod"):
            os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        handle = os.fdopen(fd, "w", encoding=encoding)
        fd = -1
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())

        ensure_no_symlink_path(parent, "父目录")
        ensure_no_symlink_path(target, "目标文件")
        os.replace(tmp_path, target)

        if os.name != "nt" and hasattr(os, "O_DIRECTORY"):
            try:
                dir_fd = os.open(
                    parent,
                    os.O_RDONLY
                    | os.O_DIRECTORY
                    | getattr(os, "O_NOFOLLOW", 0),
                )
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
    except BaseException:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return target


def read_small_text_no_follow(
    path: str | Path,
    *,
    max_bytes: int,
    encoding: str = "utf-8",
) -> str | None:
    """Read a bounded regular file while refusing every symlink component."""
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")

    target = ensure_no_symlink_path(path, "读取路径")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        fd = os.open(target, flags)
    except FileNotFoundError:
        return None

    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise PrivatePathError(f"读取目标不是常规文件：{target}")
        if file_stat.st_size > max_bytes:
            raise PrivatePathError(f"读取目标超过大小上限：{target}")

        chunks = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > max_bytes:
            raise PrivatePathError(f"读取目标超过大小上限：{target}")
        ensure_no_symlink_path(target, "读取路径")
    finally:
        os.close(fd)
    return payload.decode(encoding)


def get_ytdlp_config_dir() -> Path:
    """Return yt-dlp's first user config directory.

    yt-dlp checks ``$XDG_CONFIG_HOME/yt-dlp`` first on every supported
    platform, falling back to ``~/.config/yt-dlp`` when the variable is not
    set. Writing anywhere else can make Agent Reach and Doctor agree with each
    other while the real yt-dlp process silently ignores the setting.
    """

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    config_home = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return config_home / "yt-dlp"


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
    config_dir = shlex.quote(str(config_path.parent))
    config_file = shlex.quote(str(config_path))
    return (
        f"mkdir -p {config_dir} && "
        "{ "
        f"grep -qxF -- '--js-runtimes node' {config_file} 2>/dev/null || "
        f"printf '%s\\n' '--js-runtimes node' >> {config_file}; "
        "}"
    )

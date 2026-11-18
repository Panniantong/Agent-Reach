# -*- coding: utf-8 -*-
"""Configuration management for Agent Reach.

Stores settings in ~/.agent-reach/config.yaml. Reads never create files or
directories; the private directory is created only on the first write.
"""

import os
import stat
import sys
import tempfile
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from pathlib import Path
from typing import Any, Optional

import yaml

from agent_reach.utils.paths import (
    PrivatePathError,
    ensure_no_symlink_path,
    home_dir,
    make_private_dir,
    read_small_text_no_follow,
)

_MAX_CONFIG_BYTES = 1024 * 1024


class ConfigError(RuntimeError):
    """Base class for configuration errors safe to show to the user."""


class ConfigReadOnlyError(ConfigError):
    """Raised when code tries to mutate an explicitly read-only config."""


class ConfigSecurityError(ConfigError):
    """Raised when a config path could redirect credential reads or writes."""


def _reject_symlink(path: Path, label: str) -> None:
    try:
        ensure_no_symlink_path(path, label)
    except PrivatePathError as exc:
        raise ConfigSecurityError(str(exc)) from exc


def _atomic_write_yaml(target: Path, data: dict) -> None:
    """Atomically replace ``target`` with owner-only YAML.

    The temporary file lives beside the target so ``os.replace`` remains an
    atomic same-filesystem operation. Existing symlinks are rejected rather
    than followed or silently replaced.
    """
    _reject_symlink(target, "配置文件")
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        if sys.platform != "win32" and hasattr(os, "fchmod"):
            os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(
                data,
                handle,
                default_flow_style=False,
                allow_unicode=True,
            )
            handle.flush()
            os.fsync(handle.fileno())

        # Fail closed if a link appeared while serialization was in progress.
        # A later race is still safe: os.replace replaces a directory entry and
        # never follows the symlink into its target.
        _reject_symlink(target, "配置文件")
        os.replace(tmp_path, target)
        if sys.platform != "win32":
            os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)

        # Persist the rename where directory fsync is supported.
        if sys.platform != "win32" and hasattr(os, "O_DIRECTORY"):
            try:
                dir_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


class Config:
    """Manages Agent Reach configuration."""

    CONFIG_DIR = home_dir() / ".agent-reach"
    CONFIG_FILE = CONFIG_DIR / "config.yaml"


    def __init__(
        self,
        config_path: Optional[Path] = None,
        *,
        read_only: bool = False,
    ):
        self.config_path = Path(config_path) if config_path else self.CONFIG_FILE
        self.config_dir = self.config_path.parent
        self.read_only = read_only
        self.data: dict = {}
        self.load()

    def _ensure_dir(self):
        """Create config directory if it doesn't exist."""
        _reject_symlink(self.config_dir, "配置目录")
        make_private_dir(self.config_dir)
        _reject_symlink(self.config_dir, "配置目录")

    def load(self):
        """Load config from YAML file."""
        _reject_symlink(self.config_dir, "配置目录")
        _reject_symlink(self.config_path, "配置文件")
        try:
            payload = read_small_text_no_follow(
                self.config_path,
                max_bytes=_MAX_CONFIG_BYTES,
            )
        except PrivatePathError as exc:
            raise ConfigSecurityError(str(exc)) from exc
        if payload is None:
            self.data = {}
            return

        loaded = yaml.safe_load(payload)
        if loaded is None:
            loaded = {}
        if not isinstance(loaded, dict):
            raise ConfigError("配置文件顶层必须是对象")
        if not all(isinstance(key, str) for key in loaded):
            raise ConfigError("配置文件的键必须是字符串")
        self.data = loaded

    def save(self):
        """Save config atomically, refusing mutation in read-only mode."""
        if self.read_only:
            raise ConfigReadOnlyError("当前配置是只读的，不能保存")
        self._ensure_dir()
        if self.config_path == home_dir() / ".agent-reach" / "config.yaml":
            from agent_reach.runtime import state
            state.remember_path(self.config_path, "configuration")
        _atomic_write_yaml(self.config_path, self.data)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value. Also checks environment variables (uppercase)."""
        # Config file first
        if key in self.data:
            return self.data[key]
        # Then env var (uppercase)
        env_val = os.environ.get(key.upper())
        if env_val:
            return env_val
        return default

    @contextmanager
    def _edit(self) -> Iterator[None]:
        if self.read_only:
            raise ConfigReadOnlyError("当前配置是只读的，不能修改")

        managed = self.config_path == home_dir() / ".agent-reach" / "config.yaml"
        lock: AbstractContextManager[None]
        if managed:
            from agent_reach.runtime.browser_binding import wait_lock

            _reject_symlink(self.config_dir, "配置目录")
            lock = wait_lock("reach-config-write", wait=5.0)
        else:
            lock = nullcontext()

        with lock:
            previous = self.data
            if managed:
                self.load()
            self.data = self.data.copy()
            try:
                yield
                self.save()
            except BaseException:
                self.data = previous
                raise

    def set(self, key: str, value: Any):
        """Set a config value and save."""
        with self._edit():
            self.data[key] = value

    def delete(self, key: str):
        """Delete a config key and save."""
        with self._edit():
            self.data.pop(key, None)

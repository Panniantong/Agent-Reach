# -*- coding: utf-8 -*-
"""Configuration management for Agent Reach.

Stores settings in ~/.agent-reach/config.yaml.
Auto-creates directory on first use.
"""

import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Optional

import yaml

from agent_reach.utils.paths import make_private_dir


def _atomic_write_yaml(target: Path, data: dict) -> None:
    """Write ``data`` as YAML to ``target`` atomically and symlink-safely.

    Writes to a sibling temp file (created mode 0o600 by
    ``tempfile.mkstemp``, so credentials are never briefly world-readable)
    in the SAME directory as the target, then ``os.replace()``s it into
    place. This fixes two hazards of a naive ``O_TRUNC`` write:

    - Torn writes / corruption on failure: ``os.replace`` is atomic, so a
      crash or exception mid-write leaves the previous config untouched.
    - Symlink swap: a symlink planted at the target path is REPLACED by the
      new regular file (``os.replace`` renames the directory entry; it does
      not follow the link) instead of being written through to an
      attacker-chosen target.

    On any exception the temp file is removed and the prior file is left
    intact; the exception then propagates.
    """
    # mkstemp creates the file mode 0o600 on every platform (owner-only), so
    # there is no race window where credentials are world-readable.
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass  # fsync is best-effort; some filesystems don't support it
        if os.name != "nt":
            os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        os.replace(tmp_path, target)
    except BaseException:
        # Crash or write failure: remove the orphaned temp file so it can't
        # leak credentials, and leave the previous config untouched.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


class Config:
    """Manages Agent Reach configuration."""

    CONFIG_DIR = Path.home() / ".agent-reach"
    CONFIG_FILE = CONFIG_DIR / "config.yaml"

    # Feature → required config keys
    FEATURE_REQUIREMENTS = {
        "exa_search": ["exa_api_key"],
        "twitter_xreach": [
            "twitter_auth_token",
            "twitter_ct0",
        ],  # legacy key name; used by twitter-cli
        "groq_whisper": ["groq_api_key"],
        "openai_whisper": ["openai_api_key"],
        "github_token": ["github_token"],
    }

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = Path(config_path) if config_path else self.CONFIG_FILE
        self.config_dir = self.config_path.parent
        self.data: dict = {}
        self._ensure_dir()
        self.load()

    def _ensure_dir(self):
        """Create config directory if it doesn't exist."""
        make_private_dir(self.config_dir)

    def load(self):
        """Load config from YAML file."""
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.data = yaml.safe_load(f) or {}
        else:
            self.data = {}

    def save(self):
        """Save config to YAML file.

        Atomic and symlink-safe — see :func:`_atomic_write_yaml`. The
        previous config is left untouched if the write fails, and a symlink
        planted at the config path is replaced rather than followed.
        """
        self._ensure_dir()
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

    def set(self, key: str, value: Any):
        """Set a config value and save."""
        self.data[key] = value
        self.save()

    def delete(self, key: str):
        """Delete a config key and save."""
        self.data.pop(key, None)
        self.save()

    def is_configured(self, feature: str) -> bool:
        """Check if a feature has all required config."""
        required = self.FEATURE_REQUIREMENTS.get(feature, [])
        return all(self.get(k) for k in required)

    def get_configured_features(self) -> dict:
        """Return status of all optional features."""
        return {feature: self.is_configured(feature) for feature in self.FEATURE_REQUIREMENTS}

    def to_dict(self) -> dict:
        """Return config as dict (masks sensitive values)."""
        sensitive_markers = (
            "key",
            "token",
            "password",
            "proxy",
            "cookie",
            "secret",
            "session",
            "sessdata",
            "csrf",
            "auth",
            "cred",
            "ct0",
        )
        masked = {}
        for k, v in self.data.items():
            if any(s in k.lower() for s in sensitive_markers):
                masked[k] = f"{str(v)[:8]}..." if v else None
            else:
                masked[k] = v
        return masked

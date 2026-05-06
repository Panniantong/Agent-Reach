# -*- coding: utf-8 -*-
"""Configuration management for HiveReach.

Stores settings in ~/.hivereach/config.yaml.
Auto-creates directory on first use.
"""

import os
from pathlib import Path
from typing import Any, Optional

import yaml


class Config:
    """Manages HiveReach configuration."""

    CONFIG_DIR = Path.home() / ".hivereach"
    CONFIG_FILE = CONFIG_DIR / "config.yaml"

    # Feature → required config keys
    FEATURE_REQUIREMENTS = {
        "exa_search": ["exa_api_key"],
        "twitter_xreach": ["twitter_auth_token", "twitter_ct0"],  # legacy key name; used by bird CLI
        "groq_whisper": ["groq_api_key"],
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
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load(self):
        """Load config from YAML file."""
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.data = yaml.safe_load(f) or {}
        else:
            self.data = {}

    def save(self):
        """Save config to YAML file."""
        self._ensure_dir()
        # Create file with restricted permissions from the start to avoid
        # a race window where credentials are briefly world-readable.
        # On Windows the POSIX mode bits only affect the read-only flag;
        # full access control relies on NTFS ACLs inherited from the
        # parent directory (~/.hivereach), so we still call chmod for the
        # narrow protection it offers and accept the platform's limits.
        import stat
        try:
            fd = os.open(
                str(self.config_path),
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                stat.S_IRUSR | stat.S_IWUSR,  # 0o600
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                yaml.dump(self.data, f, default_flow_style=False, allow_unicode=True)
        except OSError:
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(self.data, f, default_flow_style=False, allow_unicode=True)
            try:
                os.chmod(self.config_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass

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
        return {
            feature: self.is_configured(feature)
            for feature in self.FEATURE_REQUIREMENTS
        }

    def to_dict(self) -> dict:
        """Return config as dict (masks sensitive values).

        Masking avoids leaking the secret's prefix (which often identifies
        the credential type, e.g. ``ghp_`` for GitHub tokens). For long
        secrets we expose only the last 4 characters so users can still
        distinguish between rotated tokens.
        """
        masked = {}
        for k, v in self.data.items():
            if any(s in k.lower() for s in ("key", "token", "password", "proxy", "cookie", "sessdata")):
                masked[k] = _mask_secret(v)
            else:
                masked[k] = v
        return masked


def _mask_secret(value: Any) -> Optional[str]:
    if not value:
        return None
    s = str(value)
    if len(s) < 16:
        return "***"
    return f"***{s[-4:]}"

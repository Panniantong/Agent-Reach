# -*- coding: utf-8 -*-
"""Configuration management for Agent Reach."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


class Config:
    """Manages Agent Reach configuration."""

    CONFIG_DIR = Path.home() / ".agent-reach"
    CONFIG_FILE = CONFIG_DIR / "config.yaml"

    FEATURE_REQUIREMENTS = {
        "twitter": ["twitter_auth_token", "twitter_ct0"],
        "github_token": ["github_token"],
    }

    def __init__(self, config_path: Path | None = None):
        self.config_path = Path(config_path) if config_path else self.CONFIG_FILE
        self.config_dir = self.config_path.parent
        self.data: dict[str, Any] = {}
        self._ensure_dir()
        self.load()

    def _ensure_dir(self) -> None:
        """Create the config directory if it does not exist."""

        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> None:
        """Load config from YAML file."""

        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as handle:
                self.data = yaml.safe_load(handle) or {}
        else:
            self.data = {}

    def save(self) -> None:
        """Save config to YAML file."""

        self._ensure_dir()
        try:
            import stat

            fd = os.open(
                str(self.config_path),
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                stat.S_IRUSR | stat.S_IWUSR,
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                yaml.safe_dump(self.data, handle, default_flow_style=False, allow_unicode=True)
        except OSError:
            with open(self.config_path, "w", encoding="utf-8") as handle:
                yaml.safe_dump(self.data, handle, default_flow_style=False, allow_unicode=True)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value, falling back to environment variables."""

        if key in self.data:
            return self.data[key]

        env_val = os.environ.get(key.upper())
        if env_val:
            return env_val
        return default

    def set(self, key: str, value: Any) -> None:
        """Set a config value and save."""

        self.data[key] = value
        self.save()

    def delete(self, key: str) -> None:
        """Delete a config key and save."""

        self.data.pop(key, None)
        self.save()

    def is_configured(self, feature: str) -> bool:
        """Check if a feature has all required config."""

        required = self.FEATURE_REQUIREMENTS.get(feature, [])
        return all(self.get(key) for key in required)

    def get_configured_features(self) -> dict[str, bool]:
        """Return status of all optional features."""

        return {
            feature: self.is_configured(feature)
            for feature in self.FEATURE_REQUIREMENTS
        }

    def to_dict(self) -> dict[str, Any]:
        """Return config as a dict with sensitive values masked."""

        masked: dict[str, Any] = {}
        for key, value in self.data.items():
            if any(marker in key.lower() for marker in ("key", "token", "password", "proxy")):
                masked[key] = f"{str(value)[:8]}..." if value else None
            else:
                masked[key] = value
        return masked

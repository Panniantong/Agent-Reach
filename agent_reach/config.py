# -*- coding: utf-8 -*-
"""Configuration management for Agent Reach.

Stores settings in ~/.agent-reach/config.yaml.
Auto-creates directory on first use.
"""

import os
from pathlib import Path
from typing import Any, Optional

import yaml


class Config:
    """Manages Agent Reach configuration."""

    CONFIG_DIR = Path.home() / ".agent-reach"
    CONFIG_FILE = CONFIG_DIR / "config.yaml"

    # Feature → required config keys
    FEATURE_REQUIREMENTS = {
        "exa_search": ["exa_api_key"],
        "reddit_proxy": ["reddit_proxy"],
        "twitter_bird": ["twitter_auth_token", "twitter_ct0"],
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
            with open(self.config_path, "r") as f:
                self.data = yaml.safe_load(f) or {}
        else:
            self.data = {}

    def save(self):
        """Save config to YAML file."""
        self._ensure_dir()
        with open(self.config_path, "w") as f:
            yaml.dump(self.data, f, default_flow_style=False, allow_unicode=True)

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
        """Return config as dict (masks sensitive values)."""
        masked = {}
        for k, v in self.data.items():
            if any(s in k.lower() for s in ("key", "token", "password", "proxy")):
                masked[k] = f"{str(v)[:8]}..." if v else None
            else:
                masked[k] = v
        return masked

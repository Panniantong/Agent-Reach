# -*- coding: utf-8 -*-
"""Configuration management for Agent Reach."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import yaml


def normalize_searxng_base_url(value: Any) -> str | Any:
    """Normalize a SearXNG instance URL to its base instance root."""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return text
    if "://" not in text:
        text = f"https://{text}"

    parsed = urlparse(text)
    if not parsed.netloc:
        return text.rstrip("/")

    path = parsed.path.rstrip("/")
    if path.endswith("/search"):
        path = path[:-7].rstrip("/")

    return urlunparse((parsed.scheme or "https", parsed.netloc, path, "", "", "")).rstrip("/")


class Config:
    """Manages Agent Reach configuration."""

    CONFIG_DIR = Path.home() / ".agent-reach"
    CONFIG_FILE = CONFIG_DIR / "config.yaml"
    ENV_ALIASES = {
        "github_token": ("GITHUB_TOKEN", "GH_TOKEN"),
        "qiita_token": ("QIITA_TOKEN",),
        "searxng_base_url": ("SEARXNG_BASE_URL",),
        "reddit_access_token": ("REDDIT_ACCESS_TOKEN", "REDDIT_BEARER_TOKEN"),
        "reddit_client_id": ("REDDIT_CLIENT_ID",),
        "reddit_client_secret": ("REDDIT_CLIENT_SECRET",),
        "reddit_user_agent": ("REDDIT_USER_AGENT",),
        "twitter_auth_token": ("TWITTER_AUTH_TOKEN", "AUTH_TOKEN"),
        "twitter_ct0": ("TWITTER_CT0", "CT0"),
    }

    FEATURE_REQUIREMENTS = {
        "searxng": ["searxng_base_url"],
        "twitter": ["twitter_auth_token", "twitter_ct0"],
        "github_token": ["github_token"],
        "reddit": ["reddit_user_agent"],
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
            value = self.data[key]
            if key == "searxng_base_url":
                return normalize_searxng_base_url(value)
            return value

        for env_key in self.ENV_ALIASES.get(key, (key.upper(),)):
            env_val = os.environ.get(env_key)
            if env_val:
                if key == "searxng_base_url":
                    return normalize_searxng_base_url(env_val)
                return env_val
        return default

    def set(self, key: str, value: Any) -> None:
        """Set a config value and save."""

        if key == "searxng_base_url":
            value = normalize_searxng_base_url(value)
        self.data[key] = value
        self.save()

    def delete(self, key: str) -> None:
        """Delete a config key and save."""

        self.data.pop(key, None)
        self.save()

    def is_configured(self, feature: str) -> bool:
        """Check if a feature has all required config."""

        if feature == "reddit":
            return bool(
                self.get("reddit_user_agent")
                and (
                    self.get("reddit_access_token")
                    or (self.get("reddit_client_id") and self.get("reddit_client_secret"))
                )
            )
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
            if any(marker in key.lower() for marker in ("key", "token", "password", "proxy", "secret")):
                masked[key] = f"{str(value)[:8]}..." if value else None
            else:
                masked[key] = value
        return masked

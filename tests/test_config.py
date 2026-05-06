# -*- coding: utf-8 -*-
"""Tests for HiveReach config module."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from hivereach.config import Config


@pytest.fixture
def tmp_config(tmp_path):
    """Create a Config with a temporary directory."""
    config_file = tmp_path / "config.yaml"
    return Config(config_path=config_file)


class TestConfig:
    def test_init_creates_dir(self, tmp_path):
        config_file = tmp_path / "subdir" / "config.yaml"
        config = Config(config_path=config_file)
        assert config_file.parent.exists()

    def test_set_and_get(self, tmp_config):
        tmp_config.set("test_key", "test_value")
        assert tmp_config.get("test_key") == "test_value"

    def test_get_default(self, tmp_config):
        assert tmp_config.get("nonexistent") is None
        assert tmp_config.get("nonexistent", "default") == "default"

    def test_get_from_env(self, tmp_config, monkeypatch):
        monkeypatch.setenv("TEST_ENV_KEY", "env_value")
        assert tmp_config.get("test_env_key") == "env_value"

    def test_config_file_priority_over_env(self, tmp_config, monkeypatch):
        monkeypatch.setenv("MY_KEY", "from_env")
        tmp_config.set("my_key", "from_config")
        assert tmp_config.get("my_key") == "from_config"

    def test_save_and_load(self, tmp_config):
        tmp_config.set("key1", "value1")
        tmp_config.set("key2", 42)

        # Create new config from same file
        config2 = Config(config_path=tmp_config.config_path)
        assert config2.get("key1") == "value1"
        assert config2.get("key2") == 42

    def test_delete(self, tmp_config):
        tmp_config.set("to_delete", "value")
        assert tmp_config.get("to_delete") == "value"
        tmp_config.delete("to_delete")
        assert tmp_config.get("to_delete") is None

    def test_is_configured(self, tmp_config):
        assert not tmp_config.is_configured("exa_search")
        tmp_config.set("exa_api_key", "test-key")
        assert tmp_config.is_configured("exa_search")

    def test_get_configured_features(self, tmp_config):
        features = tmp_config.get_configured_features()
        assert isinstance(features, dict)
        assert "exa_search" in features
        assert all(v is False for v in features.values())

    def test_to_dict_masks_sensitive(self, tmp_config):
        tmp_config.set("exa_api_key", "super-secret-key-12345")  # 21 chars
        tmp_config.set("github_token", "ghp_short")               # 9 chars
        tmp_config.set("xhs_cookie", "a1=value;web_session=abcd1234efgh5678")
        tmp_config.set("normal_setting", "visible")
        masked = tmp_config.to_dict()

        # Long secrets reveal only the last 4 chars (no prefix leak)
        assert masked["exa_api_key"] == "***2345"
        # Short secrets are fully redacted to avoid leaking length/format hints
        assert masked["github_token"] == "***"
        # Cookie-style keys are also masked (newly covered)
        assert masked["xhs_cookie"].startswith("***")
        assert "web_session" not in masked["xhs_cookie"]
        # Non-sensitive keys pass through untouched
        assert masked["normal_setting"] == "visible"

    def test_to_dict_masks_handles_empty_values(self, tmp_config):
        tmp_config.set("exa_api_key", "")
        tmp_config.set("github_token", None)
        masked = tmp_config.to_dict()
        assert masked["exa_api_key"] is None
        assert masked["github_token"] is None

    def test_save_creates_file_with_restricted_permissions(self, tmp_path):
        import stat
        import sys
        config_file = tmp_path / "secure_config.yaml"
        config = Config(config_path=config_file)
        config.set("secret_key", "my-secret")

        if sys.platform != "win32":
            mode = config_file.stat().st_mode
            # File should be owner-only read/write (0o600)
            assert not (mode & stat.S_IRGRP), "group read should not be set"
            assert not (mode & stat.S_IROTH), "other read should not be set"

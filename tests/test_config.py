# -*- coding: utf-8 -*-
"""Tests for Agent Reach config module."""

import pytest

from agent_reach.config import Config


@pytest.fixture
def tmp_config(tmp_path):
    """Create a Config with a temporary directory."""
    config_file = tmp_path / "config.yaml"
    return Config(config_path=config_file)


class TestConfig:
    def test_init_creates_dir(self, tmp_path):
        config_file = tmp_path / "subdir" / "config.yaml"
        Config(config_path=config_file)
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
        tmp_config.set("exa_api_key", "super-secret-key-12345")
        tmp_config.set("normal_setting", "visible")
        masked = tmp_config.to_dict()
        assert masked["exa_api_key"] == "super-se..."
        assert masked["normal_setting"] == "visible"

    def test_to_dict_masks_cookie_and_session_credentials(self, tmp_config):
        secrets = {
            "twitter_ct0": "csrf-secret-value",
            "xhs_cookie": "web_session=xhs-secret",
            "xueqiu_cookie": "xq_a_token=xueqiu-secret",
            "bilibili_sessdata": "bili-session-secret",
            "bilibili_csrf": "bili-csrf-secret",
            "twitter_auth_token": "twitter-auth-secret",
        }
        for key, value in secrets.items():
            tmp_config.set(key, value)

        tmp_config.set("normal_setting", "visible")
        masked = tmp_config.to_dict()

        dumped = str(masked)
        for value in secrets.values():
            assert value not in dumped
        assert masked["normal_setting"] == "visible"

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

    def test_save_tightens_existing_config_file_permissions(self, tmp_path):
        import os
        import stat
        import sys

        config_file = tmp_path / "secure_config.yaml"
        config_file.write_text("twitter_auth_token: old\n", encoding="utf-8")
        if sys.platform != "win32":
            os.chmod(config_file, 0o644)

        config = Config(config_path=config_file)
        config.set("twitter_auth_token", "new-secret")

        if sys.platform != "win32":
            mode = config_file.stat().st_mode
            assert not (mode & stat.S_IRGRP), "group read should be removed"
            assert not (mode & stat.S_IROTH), "other read should be removed"

    def test_config_dir_has_restricted_permissions(self, tmp_path):
        import stat
        import sys

        config_file = tmp_path / "private" / "config.yaml"
        Config(config_path=config_file)

        if sys.platform != "win32":
            mode = config_file.parent.stat().st_mode
            assert not (mode & stat.S_IRGRP), "group read should not be set"
            assert not (mode & stat.S_IXGRP), "group execute should not be set"
            assert not (mode & stat.S_IROTH), "other read should not be set"
            assert not (mode & stat.S_IXOTH), "other execute should not be set"

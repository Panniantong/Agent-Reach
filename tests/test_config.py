# -*- coding: utf-8 -*-
"""Tests for Agent Reach config module."""

import pytest

from agent_reach.config import Config, ConfigReadOnlyError, ConfigSecurityError
from agent_reach.utils import paths


@pytest.fixture
def tmp_config(tmp_path):
    """Create a Config with a temporary directory."""
    config_file = tmp_path / "config.yaml"
    return Config(config_path=config_file)


class TestConfig:
    def test_init_is_read_only_on_disk_until_first_save(self, tmp_path):
        config_file = tmp_path / "subdir" / "config.yaml"
        Config(config_path=config_file)
        assert not config_file.parent.exists()

    def test_read_only_config_never_creates_or_changes_files(self, tmp_path):
        config_file = tmp_path / "subdir" / "config.yaml"
        config = Config(config_path=config_file, read_only=True)

        assert config.get("missing") is None
        assert not config_file.parent.exists()
        with pytest.raises(ConfigReadOnlyError):
            config.set("secret", "value")
        assert not config_file.parent.exists()

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
        config = Config(config_path=config_file)
        config.set("key", "value")

        if sys.platform != "win32":
            mode = config_file.parent.stat().st_mode
            assert not (mode & stat.S_IRGRP), "group read should not be set"
            assert not (mode & stat.S_IXGRP), "group execute should not be set"
            assert not (mode & stat.S_IROTH), "other read should not be set"
            assert not (mode & stat.S_IXOTH), "other execute should not be set"

    def test_config_dir_under_symlinked_home_initializes_and_saves(
        self, tmp_path, monkeypatch
    ):
        """Regression: a symlinked ``$HOME`` used to abort every command with
        ConfigSecurityError. The default CONFIG_DIR resolves the home prefix,
        so Config now initializes and persists there normally."""
        real_home = tmp_path / "real-home"
        real_home.mkdir(mode=0o700)
        linked_home = tmp_path / "linked-home"
        try:
            linked_home.symlink_to(real_home, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")

        monkeypatch.setattr(
            paths.Path, "home", classmethod(lambda cls: linked_home)
        )
        from agent_reach.utils.paths import user_home

        config_file = user_home() / ".agent-reach" / "config.yaml"
        assert not config_file.is_relative_to(linked_home)

        config = Config(config_path=config_file)
        config.set("key", "value")

        assert config.get("key") == "value"
        assert config_file.is_relative_to(real_home)

    def test_load_refuses_symlink_config_path(self, tmp_path):
        victim = tmp_path / "victim.yaml"
        victim.write_text("secret: victim-data\n", encoding="utf-8")
        config_file = tmp_path / "config.yaml"
        try:
            config_file.symlink_to(victim)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")

        with pytest.raises(ConfigSecurityError, match="符号链接"):
            Config(config_path=config_file)
        assert victim.read_text(encoding="utf-8") == "secret: victim-data\n"

    def test_save_refuses_symlink_inserted_after_load(self, tmp_path):
        victim = tmp_path / "victim.yaml"
        victim.write_text("secret: victim-data\n", encoding="utf-8")
        config_file = tmp_path / "config.yaml"
        config = Config(config_path=config_file)
        try:
            config_file.symlink_to(victim)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")

        with pytest.raises(ConfigSecurityError, match="符号链接"):
            config.set("secret", "new-data")

        assert config_file.is_symlink()
        assert victim.read_text(encoding="utf-8") == "secret: victim-data\n"

    def test_config_directory_symlink_is_rejected(self, tmp_path):
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        linked_dir = tmp_path / "linked"
        try:
            linked_dir.symlink_to(real_dir, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")

        with pytest.raises(ConfigSecurityError, match="配置目录"):
            Config(config_path=linked_dir / "config.yaml")
        assert list(real_dir.iterdir()) == []

    def test_config_ancestor_symlink_is_rejected(self, tmp_path):
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        linked_root = tmp_path / "linked-root"
        try:
            linked_root.symlink_to(real_dir, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")

        with pytest.raises(ConfigSecurityError, match="符号链接"):
            Config(config_path=linked_root / "nested" / "config.yaml")

    def test_config_load_refuses_non_regular_file(self, tmp_path):
        import os

        if not hasattr(os, "mkfifo"):
            pytest.skip("FIFOs are not supported on this platform")
        config_file = tmp_path / "config.yaml"
        os.mkfifo(config_file)

        with pytest.raises(ConfigSecurityError, match="常规文件"):
            Config(config_path=config_file)

    def test_config_load_is_bounded(self, tmp_path, monkeypatch):
        import agent_reach.config as config_module

        config_file = tmp_path / "config.yaml"
        config_file.write_text("secret: too-long\n", encoding="utf-8")
        monkeypatch.setattr(config_module, "_MAX_CONFIG_BYTES", 4)

        with pytest.raises(ConfigSecurityError, match="大小上限"):
            Config(config_path=config_file)

    def test_save_preserves_previous_file_on_serialization_failure(
        self, tmp_path, monkeypatch
    ):
        config_file = tmp_path / "config.yaml"
        config = Config(config_path=config_file)
        config.set("keep_key", "keep_value")
        previous = config_file.read_bytes()

        def fail_dump(*args, **kwargs):
            raise RuntimeError("simulated write failure")

        monkeypatch.setattr("agent_reach.config.yaml.safe_dump", fail_dump)
        with pytest.raises(RuntimeError, match="simulated"):
            config.set("new_key", "new_value")

        assert config_file.read_bytes() == previous
        assert config.get("new_key") is None
        assert list(tmp_path.glob(".config.yaml.*.tmp")) == []

    def test_atomic_temp_file_is_created_next_to_custom_config_path(
        self, tmp_path, monkeypatch
    ):
        import tempfile

        config_file = tmp_path / "custom" / "nested" / "settings.yaml"
        config = Config(config_path=config_file)
        observed = {}
        real_mkstemp = tempfile.mkstemp

        def spy_mkstemp(*args, **kwargs):
            observed["dir"] = kwargs.get("dir")
            return real_mkstemp(*args, **kwargs)

        monkeypatch.setattr("agent_reach.config.tempfile.mkstemp", spy_mkstemp)
        config.set("key", "value")

        assert observed["dir"] == str(config_file.parent)
        assert config_file.read_text(encoding="utf-8") == "key: value\n"

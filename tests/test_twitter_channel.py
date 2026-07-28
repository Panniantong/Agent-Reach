# -*- coding: utf-8 -*-
"""Twitter health checks must never trigger upstream browser-cookie fallback."""

import os
from unittest.mock import Mock, patch

from agent_reach.backends import OpenCLIStatus
from agent_reach.channels.twitter import (
    TwitterChannel,
    twitter_cli_child_env,
)


def _which(*present):
    return lambda name: f"/usr/local/bin/{name}" if name in present else None


def test_twitter_cli_without_explicit_auth_is_unverified():
    channel = TwitterChannel()
    with patch("shutil.which", side_effect=_which("twitter")), patch(
        "subprocess.run",
        side_effect=AssertionError("twitter status must not run"),
    ):
        status, message = channel.check()

    assert status == "warn"
    assert "Cookie-Editor" in message
    assert channel.active_backend is None


def test_saved_credentials_are_recognised_without_starting_upstream(
    monkeypatch,
):
    config = Mock()
    config.get.side_effect = lambda key: {
        "twitter_auth_token": "saved-auth-token",
        "twitter_ct0": "saved-ct0",
    }.get(key)
    monkeypatch.delenv("TWITTER_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWITTER_CT0", raising=False)

    with patch("shutil.which", side_effect=_which("twitter")), patch(
        "subprocess.run"
    ) as run:
        channel = TwitterChannel()
        status, message = channel.check(config)

    assert status == "warn"
    assert "已配置" in message
    assert "不会执行" in message
    assert channel.active_backend is None
    run.assert_not_called()
    assert "TWITTER_AUTH_TOKEN" not in os.environ
    assert "TWITTER_CT0" not in os.environ


def test_child_env_keeps_existing_shell_credentials_authoritative(
    monkeypatch,
):
    config = Mock()
    config.get.side_effect = lambda key: {
        "twitter_auth_token": "saved-auth-token",
        "twitter_ct0": "saved-ct0",
    }.get(key)
    monkeypatch.setenv("TWITTER_AUTH_TOKEN", "shell-auth-token")
    monkeypatch.setenv("TWITTER_CT0", "shell-ct0")

    assert twitter_cli_child_env(config) == {}
    assert os.environ["TWITTER_AUTH_TOKEN"] == "shell-auth-token"
    assert os.environ["TWITTER_CT0"] == "shell-ct0"


def test_child_env_supplies_only_missing_saved_credentials(monkeypatch):
    config = Mock()
    config.get.side_effect = lambda key: {
        "twitter_auth_token": "saved-auth-token",
        "twitter_ct0": "saved-ct0",
    }.get(key)
    monkeypatch.setenv("TWITTER_AUTH_TOKEN", "shell-auth-token")
    monkeypatch.delenv("TWITTER_CT0", raising=False)

    assert twitter_cli_child_env(config) == {"TWITTER_CT0": "saved-ct0"}


def test_bird_with_explicit_env_remains_unverified(monkeypatch):
    monkeypatch.setenv("AUTH_TOKEN", "explicit-auth")
    monkeypatch.setenv("CT0", "explicit-ct0")
    with patch("shutil.which", side_effect=_which("bird")), patch(
        "subprocess.run",
        side_effect=AssertionError("bird check must not run"),
    ):
        channel = TwitterChannel()
        status, message = channel.check()

    assert status == "warn"
    assert "未实时验证" in message
    assert channel.active_backend is None


def test_bird_without_explicit_env_is_warn(monkeypatch):
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CT0", raising=False)
    with patch("shutil.which", side_effect=_which("bird")):
        channel = TwitterChannel()
        status, message = channel.check()

    assert status == "warn"
    assert "未检测到显式" in message
    assert channel.active_backend is None


def test_nothing_installed_returns_install_hint():
    channel = TwitterChannel()
    with patch("shutil.which", return_value=None):
        status, message = channel.check()

    assert status == "warn"
    assert "twitter-cli" in message
    assert channel.active_backend is None


def test_opencli_bridge_ready_is_unverified_for_twitter():
    with patch(
        "agent_reach.backends.opencli_status",
        return_value=OpenCLIStatus(
            installed=True,
            extension_connected=True,
            version="1.8.6",
        ),
    ):
        status, message = TwitterChannel()._check_opencli()

    assert status == "warn"
    assert "桥接已连接" in message
    assert "登录态和实际命令未实时验证" in message


def test_verified_backend_result_wins_over_unverified_twitter_cli():
    channel = TwitterChannel()
    with patch.object(
        TwitterChannel,
        "_check_twitter_cli",
        return_value=("warn", "twitter-cli 未验证"),
    ), patch.object(
        TwitterChannel,
        "_check_opencli",
        return_value=("ok", "OpenCLI 可用"),
    ), patch.object(TwitterChannel, "_check_bird", return_value=None):
        status, message = channel.check()

    assert status == "ok"
    assert message == "OpenCLI 可用"
    assert channel.active_backend == "OpenCLI"


def test_all_warn_returns_first_warning_without_active_backend():
    channel = TwitterChannel()
    with patch.object(
        TwitterChannel,
        "_check_twitter_cli",
        return_value=("warn", "twitter-cli 未验证"),
    ), patch.object(
        TwitterChannel,
        "_check_opencli",
        return_value=("warn", "扩展未连接"),
    ), patch.object(TwitterChannel, "_check_bird", return_value=None):
        status, message = channel.check()

    assert status == "warn"
    assert message == "twitter-cli 未验证"
    assert channel.active_backend is None

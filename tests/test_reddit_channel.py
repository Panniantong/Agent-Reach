# -*- coding: utf-8 -*-
"""Dedicated tests for Reddit's read-only multi-backend health check."""

import json
import time
from unittest.mock import Mock, patch

import pytest

from agent_reach.channels.reddit import RedditChannel


def test_can_handle_matches_reddit_hosts():
    channel = RedditChannel()
    for url in [
        "https://reddit.com/r/python",
        "https://www.reddit.com/r/python/comments/abc/title/",
        "https://old.reddit.com/r/python",
        "https://redd.it/abc123",
        "HTTPS://REDDIT.COM/r/Python",
    ]:
        assert channel.can_handle(url) is True, url


def test_can_handle_rejects_non_reddit():
    channel = RedditChannel()
    for url in ["https://example.com/r/python", "https://twitter.com/u", ""]:
        assert channel.can_handle(url) is False, url


def test_check_rdt_returns_none_when_not_installed():
    with patch("shutil.which", return_value=None):
        assert RedditChannel()._check_rdt() is None


def test_check_rdt_missing_credential_is_warn():
    with patch("shutil.which", return_value="/usr/local/bin/rdt"):
        status, message = RedditChannel()._check_rdt()

    assert status == "warn"
    assert "Cookie-Editor" in message


def test_check_rdt_saved_credential_is_unverified_not_false_ok(
    isolated_home,
):
    path = isolated_home / ".config" / "rdt-cli" / "credential.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "cookies": {"reddit_session": "explicit"},
                "saved_at": time.time(),
            }
        ),
        encoding="utf-8",
    )
    with patch("shutil.which", return_value="/usr/local/bin/rdt"), patch(
        "subprocess.run"
    ) as run:
        status, message = RedditChannel()._check_rdt()

    assert status == "warn"
    assert "未实时验证" in message
    run.assert_not_called()


def test_check_rdt_stale_credential_is_not_refreshed(isolated_home):
    path = isolated_home / ".config" / "rdt-cli" / "credential.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "cookies": {"reddit_session": "explicit"},
                "saved_at": time.time() - 8 * 86400,
            }
        ),
        encoding="utf-8",
    )
    before = path.read_bytes()
    with patch("shutil.which", return_value="/usr/local/bin/rdt"), patch(
        "subprocess.run"
    ) as run:
        status, message = RedditChannel()._check_rdt()

    assert status == "warn"
    assert "超过 7 天" in message
    assert path.read_bytes() == before
    run.assert_not_called()


def test_check_rdt_unparseable_credential_is_warn(isolated_home):
    path = isolated_home / ".config" / "rdt-cli" / "credential.json"
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")
    with patch("shutil.which", return_value="/usr/local/bin/rdt"):
        status, message = RedditChannel()._check_rdt()

    assert status == "warn"
    assert "无法安全解析" in message


def test_check_rdt_refuses_symlink_credential(isolated_home):
    victim = isolated_home / "victim.json"
    victim.write_text('{"secret": "do-not-read"}', encoding="utf-8")
    path = isolated_home / ".config" / "rdt-cli" / "credential.json"
    path.parent.mkdir(parents=True)
    try:
        path.symlink_to(victim)
    except OSError:
        pytest.skip("symlinks are not supported on this platform")
    with patch("shutil.which", return_value="/usr/local/bin/rdt"):
        status, message = RedditChannel()._check_rdt()

    assert status == "warn"
    assert "符号链接" in message


def test_check_rdt_refuses_ancestor_symlink(isolated_home):
    victim_dir = isolated_home / "victim-config"
    credential_path = victim_dir / "rdt-cli" / "credential.json"
    credential_path.parent.mkdir(parents=True)
    credential_path.write_text(
        '{"cookies": {"reddit_session": "do-not-read"}}',
        encoding="utf-8",
    )
    try:
        (isolated_home / ".config").symlink_to(
            victim_dir,
            target_is_directory=True,
        )
    except OSError:
        pytest.skip("symlinks are not supported on this platform")

    with patch("shutil.which", return_value="/usr/local/bin/rdt"):
        status, message = RedditChannel()._check_rdt()

    assert status == "warn"
    assert "符号链接" in message


def _opencli(installed=True, broken=False, ready=True, hint=""):
    return Mock(installed=installed, broken=broken, ready=ready, hint=hint)


def test_check_opencli_not_installed_is_none():
    with patch(
        "agent_reach.backends.opencli_status",
        return_value=_opencli(installed=False),
    ):
        assert RedditChannel()._check_opencli() is None


def test_check_opencli_broken_is_error():
    with patch(
        "agent_reach.backends.opencli_status",
        return_value=_opencli(broken=True, hint="reinstall opencli"),
    ):
        status, message = RedditChannel()._check_opencli()
    assert status == "error"
    assert message == "reinstall opencli"


def test_check_opencli_bridge_ready_is_unverified():
    with patch(
        "agent_reach.backends.opencli_status",
        return_value=_opencli(ready=True),
    ):
        status, message = RedditChannel()._check_opencli()
    assert status == "warn"
    assert "桥接已连接" in message
    assert "登录态和实际命令未实时验证" in message


def test_check_opencli_installed_not_ready_is_warn():
    with patch(
        "agent_reach.backends.opencli_status",
        return_value=_opencli(ready=False, hint="connect the extension"),
    ):
        status, message = RedditChannel()._check_opencli()
    assert status == "warn"
    assert message == "connect the extension"


def test_check_prefers_ok_over_warn_regardless_of_probe_order():
    channel = RedditChannel()
    with patch.object(
        channel, "_check_opencli", return_value=("warn", "opencli sleepy")
    ), patch.object(
        channel, "_check_rdt", return_value=("ok", "rdt ready")
    ):
        status, message = channel.check()

    assert status == "ok"
    assert message == "rdt ready"
    assert channel.active_backend == "rdt-cli"


def test_check_warn_has_no_active_backend():
    channel = RedditChannel()
    with patch.object(
        channel, "_check_opencli", return_value=("warn", "not ready")
    ), patch.object(
        channel, "_check_rdt", return_value=("warn", "unverified")
    ):
        status, message = channel.check()

    assert status == "warn"
    assert message == "not ready"
    assert channel.active_backend is None


def test_check_all_errors_returns_error_and_no_active_backend():
    channel = RedditChannel()
    with patch.object(
        channel, "_check_opencli", return_value=("error", "e1")
    ), patch.object(channel, "_check_rdt", return_value=("error", "e2")):
        status, message = channel.check()

    assert status == "error"
    assert "e1" in message and "e2" in message
    assert channel.active_backend is None


def test_check_no_backend_installed_is_off():
    channel = RedditChannel()
    with patch.object(channel, "_check_opencli", return_value=None), patch.object(
        channel, "_check_rdt", return_value=None
    ):
        status, message = channel.check()

    assert status == "off"
    assert "零配置" in message
    assert channel.active_backend is None

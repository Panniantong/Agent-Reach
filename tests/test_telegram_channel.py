# -*- coding: utf-8 -*-

from unittest.mock import Mock, patch

from agent_reach.channels.telegram import TelegramChannel


def _cp(stdout="", stderr="", returncode=0):
    m = Mock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = returncode
    return m


def test_can_handle_common_urls():
    ch = TelegramChannel()
    assert ch.can_handle("https://t.me/durov")
    assert ch.can_handle("https://t.me/s/durov")
    assert ch.can_handle("https://telegram.me/joinchat/abc")
    assert not ch.can_handle("https://discord.com/channels/1")


def test_check_tg_cli_found_and_auth_ok():
    """tg found + `tg status` exit 0 → ok."""
    channel = TelegramChannel()
    with patch("shutil.which", side_effect=lambda name: "/usr/local/bin/tg" if name == "tg" else None), patch(
        "subprocess.run",
        return_value=_cp(stdout="ok: true\ndata:\n  authenticated: true\n", returncode=0),
    ):
        status, message = channel.check()
    assert status == "ok"
    assert "tg-cli" in message
    assert "完整可用" in message
    assert channel.active_backend == "tg-cli"


def test_check_tg_cli_found_not_logged_in():
    """tg found + non-zero exit (no session) → warn about login."""
    channel = TelegramChannel()
    with patch("shutil.which", side_effect=lambda name: "/usr/local/bin/tg" if name == "tg" else None), patch(
        "subprocess.run",
        return_value=_cp(stdout="ok: false\nerror:\n  code: not_authenticated\n", returncode=1),
    ):
        status, message = channel.check()
    assert status == "warn"
    assert "未登录" in message
    assert "tg chats" in message
    assert channel.active_backend == "tg-cli"


def test_check_tg_cli_broken_reports_error_with_reinstall_hint():
    """which 命中但 exec 抛 FileNotFoundError（venv 断链）→ error + 重装处方。"""
    channel = TelegramChannel()
    with patch(
        "shutil.which",
        side_effect=lambda name: "/usr/local/bin/tg" if name == "tg" else None,
    ), patch("subprocess.run", side_effect=FileNotFoundError("/usr/local/bin/tg")):
        status, message = channel.check()
    assert status == "error"
    assert "无法执行" in message
    assert "uv tool install --force kabi-tg-cli" in message
    assert "pipx reinstall kabi-tg-cli" in message
    assert channel.active_backend is None


def test_check_nothing_installed():
    """No tg-cli → off with install hint."""
    channel = TelegramChannel()
    with patch("shutil.which", return_value=None):
        status, message = channel.check()
    assert status == "off"
    assert "kabi-tg-cli" in message
    assert channel.active_backend is None

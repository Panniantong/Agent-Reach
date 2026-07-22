# -*- coding: utf-8 -*-

from unittest.mock import Mock, patch

from agent_reach.channels.discord import DiscordChannel


def _cp(stdout="", stderr="", returncode=0):
    m = Mock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = returncode
    return m


def test_can_handle_common_urls():
    ch = DiscordChannel()
    assert ch.can_handle("https://discord.com/channels/123/456")
    assert ch.can_handle("https://discord.gg/abcdef")
    assert ch.can_handle("https://discordapp.com/channels/1")
    assert not ch.can_handle("https://t.me/some_channel")


def test_check_discord_cli_found_and_auth_ok():
    """discord found + `discord status` exit 0 → ok."""
    channel = DiscordChannel()
    with patch("shutil.which", side_effect=lambda name: "/usr/local/bin/discord" if name == "discord" else None), patch(
        "subprocess.run",
        return_value=_cp(stdout="ok: true\ndata:\n  authenticated: true\n", returncode=0),
    ):
        status, message = channel.check()
    assert status == "ok"
    assert "discord-cli" in message
    assert "完整可用" in message
    assert channel.active_backend == "discord-cli"


def test_check_discord_cli_found_auth_missing():
    """discord found + not_authenticated (non-zero exit) → warn about auth."""
    channel = DiscordChannel()
    with patch("shutil.which", side_effect=lambda name: "/usr/local/bin/discord" if name == "discord" else None), patch(
        "subprocess.run",
        return_value=_cp(stdout="ok: false\nerror:\n  code: not_authenticated\n", returncode=1),
    ):
        status, message = channel.check()
    assert status == "warn"
    assert "未认证" in message
    assert "discord auth --save" in message
    # 未认证是业务态：工具进程活着，后端仍归属 discord-cli
    assert channel.active_backend == "discord-cli"


def test_check_discord_cli_broken_reports_error_with_reinstall_hint():
    """which 命中但 exec 抛 FileNotFoundError（venv 断链）→ error + 重装处方。"""
    channel = DiscordChannel()
    with patch(
        "shutil.which",
        side_effect=lambda name: "/usr/local/bin/discord" if name == "discord" else None,
    ), patch("subprocess.run", side_effect=FileNotFoundError("/usr/local/bin/discord")):
        status, message = channel.check()
    assert status == "error"
    assert "无法执行" in message
    assert "uv tool install --force kabi-discord-cli" in message
    assert "pipx reinstall kabi-discord-cli" in message
    assert channel.active_backend is None


def test_check_nothing_installed():
    """No discord-cli → off with install hint."""
    channel = DiscordChannel()
    with patch("shutil.which", return_value=None):
        status, message = channel.check()
    assert status == "off"
    assert "kabi-discord-cli" in message
    assert channel.active_backend is None

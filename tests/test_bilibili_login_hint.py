"""The Bilibili login hint must name a command the user can actually run."""

from __future__ import annotations

from agent_reach.channels.bilibili import BilibiliChannel, _BILI_LOGIN_HINT


def test_hint_names_the_agent_reach_login_command():
    assert "agent-reach login bilibili" in _BILI_LOGIN_HINT


def test_hint_does_not_name_the_private_venv_binary():
    """`bili` is installed under ~/.agent-reach/tools and is never on PATH."""
    assert "`bili login`" not in _BILI_LOGIN_HINT


def test_hint_names_the_channel_login_command_from_the_channel_contract():
    """Keep the hint in step with the command `agent-reach channels` reports."""
    channel = BilibiliChannel()
    assert channel.login_argv and channel.login_argv[0] == "bili"
    # The user-facing form is `agent-reach login <channel>`, not the tool binary.
    assert f"agent-reach login {channel.name}" in _BILI_LOGIN_HINT

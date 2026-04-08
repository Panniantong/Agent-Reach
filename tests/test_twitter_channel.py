# -*- coding: utf-8 -*-
"""Tests for the Twitter/X channel."""

from unittest.mock import Mock, patch

from agent_reach.channels.twitter import TwitterChannel


def _cp(stdout="", stderr="", returncode=0):
    mock = Mock()
    mock.stdout = stdout
    mock.stderr = stderr
    mock.returncode = returncode
    return mock


def test_check_reports_warn_when_not_installed():
    with patch("agent_reach.channels.twitter.find_command", return_value=None), patch(
        "shutil.which", return_value=None
    ):
        status, message = TwitterChannel().check()
    assert status == "warn"
    assert "uv tool install twitter-cli" in message


def test_check_reports_ok_when_authenticated():
    channel = TwitterChannel()
    with patch(
        "agent_reach.channels.twitter.find_command",
        return_value="/usr/local/bin/twitter",
    ), patch(
        "subprocess.run",
        return_value=_cp(stdout="ok: true\nusername: testuser\n", returncode=0),
    ):
        status, message = channel.check()
    assert status == "ok"
    assert "tweet reads" in message


def test_check_reports_warn_when_not_authenticated():
    channel = TwitterChannel()
    with patch(
        "agent_reach.channels.twitter.find_command",
        return_value="/usr/local/bin/twitter",
    ), patch(
        "subprocess.run",
        return_value=_cp(stderr="ok: false\nerror:\n  code: not_authenticated\n", returncode=1),
    ):
        status, message = channel.check()
    assert status == "warn"
    assert "configure twitter-cookies" in message

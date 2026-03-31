# -*- coding: utf-8 -*-

from unittest.mock import patch, Mock

from agent_reach.channels.twitter import TwitterChannel


def _cp(stdout="", stderr="", returncode=0):
    m = Mock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = returncode
    return m


def test_check_twitter_cli_found_and_auth_ok():
    """twitter-cli found + twitter status ok → ok."""
    channel = TwitterChannel()
    with patch("shutil.which", return_value="/usr/local/bin/twitter"), patch(
        "subprocess.run",
        return_value=_cp(stdout="ok: true\nusername: testuser\n", returncode=0),
    ):
        status, message = channel.check()
    assert status == "ok"
    assert "完整可用" in message


def test_check_twitter_cli_found_auth_missing():
    """twitter-cli found + not_authenticated → warn about auth."""
    channel = TwitterChannel()
    with patch("shutil.which", return_value="/usr/local/bin/twitter"), patch(
        "subprocess.run",
        return_value=_cp(
            stderr="ok: false\nerror:\n  code: not_authenticated\n",
            returncode=1,
        ),
    ):
        status, message = channel.check()
    assert status == "warn"
    assert "未认证" in message


def test_check_twitter_cli_not_found():
    """twitter-cli not found → warn with install hint."""
    channel = TwitterChannel()
    with patch("shutil.which", return_value=None):
        status, message = channel.check()
    assert status == "warn"
    assert "twitter-cli" in message


def test_check_twitter_cli_generic_failure():
    """twitter status returns 1 without not_authenticated → generic warn."""
    channel = TwitterChannel()
    with patch("shutil.which", return_value="/usr/local/bin/twitter"), patch(
        "subprocess.run",
        return_value=_cp(stderr="some error\n", returncode=1),
    ):
        status, message = channel.check()
    assert status == "warn"
    assert "认证检查失败" in message


def test_check_twitter_cli_exception():
    """twitter status throws exception → warn."""
    channel = TwitterChannel()
    with patch("shutil.which", return_value="/usr/local/bin/twitter"), patch(
        "subprocess.run", side_effect=Exception("timeout"),
    ):
        status, message = channel.check()
    assert status == "warn"
    assert "连接失败" in message

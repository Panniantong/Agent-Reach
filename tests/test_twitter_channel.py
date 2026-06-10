# -*- coding: utf-8 -*-

from unittest.mock import patch, Mock

from agent_reach.channels.twitter import TwitterChannel


def _cp(stdout="", stderr="", returncode=0):
    m = Mock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = returncode
    return m


# --- twitter-cli tests ---

def test_check_twitter_cli_found_and_auth_ok():
    """twitter-cli found + twitter status ok → ok."""
    channel = TwitterChannel()
    with patch("shutil.which", side_effect=lambda name: "/usr/local/bin/twitter" if name == "twitter" else None), patch(
        "subprocess.run",
        return_value=_cp(stdout="ok: true\nusername: testuser\n", returncode=0),
    ):
        status, message = channel.check()
    assert status == "ok"
    assert "twitter-cli" in message
    assert "完整可用" in message


def test_check_twitter_cli_found_auth_missing():
    """twitter-cli found + not_authenticated → warn about auth."""
    channel = TwitterChannel()
    with patch("shutil.which", side_effect=lambda name: "/usr/local/bin/twitter" if name == "twitter" else None), patch(
        "subprocess.run",
        return_value=_cp(
            stderr="ok: false\nerror:\n  code: not_authenticated\n",
            returncode=1,
        ),
    ):
        status, message = channel.check()
    assert status == "warn"
    assert "未认证" in message


# --- bird CLI fallback tests ---

def test_check_bird_fallback_auth_ok():
    """No twitter-cli, but bird found + bird check ok → ok."""
    channel = TwitterChannel()
    def which_side_effect(name):
        if name == "bird":
            return "/usr/local/bin/bird"
        return None
    with patch("shutil.which", side_effect=which_side_effect), patch(
        "subprocess.run",
        return_value=_cp(stdout="Authenticated as @user\n", returncode=0),
    ):
        status, message = channel.check()
    assert status == "ok"
    assert "bird" in message


def test_check_bird_fallback_auth_missing():
    """No twitter-cli, bird found but Missing credentials → warn."""
    channel = TwitterChannel()
    def which_side_effect(name):
        if name == "bird":
            return "/usr/local/bin/bird"
        return None
    with patch("shutil.which", side_effect=which_side_effect), patch(
        "subprocess.run",
        return_value=_cp(stderr="Missing credentials\n", returncode=1),
    ):
        status, message = channel.check()
    assert status == "warn"
    assert "未配置认证" in message


# --- neither installed ---

def test_check_nothing_installed():
    """Neither twitter-cli nor bird → warn with install hint."""
    channel = TwitterChannel()
    with patch("shutil.which", return_value=None):
        status, message = channel.check()
    assert status == "warn"
    assert "twitter-cli" in message


# --- twitter-cli preferred over bird ---

def test_twitter_cli_preferred_over_bird():
    """When both are installed, twitter-cli is used."""
    channel = TwitterChannel()
    def which_side_effect(name):
        if name == "twitter":
            return "/usr/local/bin/twitter"
        if name == "bird":
            return "/usr/local/bin/bird"
        return None
    with patch("shutil.which", side_effect=which_side_effect), patch(
        "subprocess.run",
        return_value=_cp(stdout="ok: true\n", returncode=0),
    ):
        status, message = channel.check()
    assert status == "ok"
    assert "twitter-cli" in message

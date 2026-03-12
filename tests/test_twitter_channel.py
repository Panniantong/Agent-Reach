# -*- coding: utf-8 -*-

from unittest.mock import patch, Mock

from agent_reach.channels.twitter import _detect_xreach_version, TwitterChannel


def _cp(stdout="", stderr="", returncode=0):
    m = Mock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = returncode
    return m


def test_detect_xreach_version_prefers_npm_when_cli_version_is_stale():
    with patch("shutil.which", return_value="/opt/homebrew/bin/npm"), patch(
        "subprocess.run",
        side_effect=[
            _cp(stdout="0.3.0\n"),
            _cp(stdout='{"dependencies":{"xreach-cli":{"version":"0.3.2"}}}'),
        ],
    ):
        assert _detect_xreach_version("/opt/homebrew/bin/xreach") == "0.3.2"


def test_twitter_channel_does_not_false_warn_when_npm_has_newer_xreach():
    channel = TwitterChannel()
    with patch("shutil.which", side_effect=lambda name: "/opt/homebrew/bin/xreach" if name == "xreach" else "/opt/homebrew/bin/npm"), patch(
        "subprocess.run",
        side_effect=[
            _cp(stdout="0.3.0\n"),
            _cp(stdout='{"dependencies":{"xreach-cli":{"version":"0.3.2"}}}'),
            _cp(stdout="authenticated\n", returncode=0),
        ],
    ):
        status, message = channel.check()
    assert status == "ok"
    assert "完整可用" in message
